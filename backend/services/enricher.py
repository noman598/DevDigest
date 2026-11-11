# backend/services/enricher.py
from datetime import datetime
from typing import Literal, Optional
import asyncio

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from config import config
from security.guardrails import sanitize_untrusted_scraped_data, validate_tool_arguments
from services.llm import BudgetUsageCallback, is_within_budget
from storage.db import SessionLocal as get_session
from storage.models import ContentEnrichment, ContentItem, PipelineStatus
from tools.hn_tools import fetch_hn_discussion, search_hn_discussions
from utils.logger import log

ENRICHMENT_MODEL = getattr(config, "GEMINI_MODEL", "gemini-3.5-flash-lite")

# Tools available to the Enrichment Agent
AVAILABLE_TOOLS = [fetch_hn_discussion, search_hn_discussions]
TOOL_MAP = {t.name: t for t in AVAILABLE_TOOLS}


class EnrichmentResult(BaseModel):
    title: str = Field(description="clean readable repository or article title")
    summary: str = Field(
        description="2-3 sentence summary of what this does, who it's for, why it matters, and developer sentiment if available"
    )
    tech_stack: list[str] = Field(default=[], description="specific technologies/frameworks used or mentioned")
    topics: list[str] = Field(default=[], description="broad topic categories (e.g. AI/ML, DevOps, Systems, LLMs)")
    use_case: Literal["library", "tool", "tutorial", "research", "framework", "dataset", "announcement", "other"] = Field(
        description="primary classification of the content"
    )


# Structured output synthesis prompt
_STRUCTURED_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert technical content analyst. Analyze the following developer content and any "
        "tool research findings (such as Hacker News community sentiment and developer reactions). "
        "Extract accurate, structured metadata and synthesize a concise, high-signal summary.",
    ),
    ("human", "Developer item to analyze:\n\n{content_text}"),
])


def _get_base_llm(content_item_id: Optional[str] = None):
    callbacks = [
        BudgetUsageCallback(
            operation="enrichment",
            provider="gemini",
            content_item_id=content_item_id,
        )
    ]
    return ChatGoogleGenerativeAI(
        model=ENRICHMENT_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0.1,
        max_output_tokens=1024,
        callbacks=callbacks,
    )


def _build_content_text(raw: dict) -> str:
    """Formats raw item data whether it is from GitHub, Hacker News, or an RSS source."""
    source = raw.get("source", "")
    title = raw.get("title", "")
    desc = raw.get("description") or "N/A"
    meta = raw.get("metadata", {})

    lines = [
        f"Source: {source}",
        f"Title: {title}",
        f"Description: {desc}",
    ]

    # Hacker News metadata
    if "score" in meta:
        lines.append(f"HN Score: {meta.get('score')} points")
    if "comments_count" in meta:
        lines.append(f"HN Comments count: {meta.get('comments_count')}")
    if "by" in meta:
        lines.append(f"Author: @{meta.get('by')}")
    if "id" in meta:
        lines.append(f"HN Story ID: {meta.get('id')}")
    if "hn_url" in meta:
        lines.append(f"HN Discussion URL: {meta.get('hn_url')}")

    # GitHub / RSS metadata
    if "language" in meta:
        lines.append(f"Language: {meta.get('language')}")
    if "total_stars" in meta:
        lines.append(f"Total stars: {meta.get('total_stars')}")
    if "stars_today" in meta:
        lines.append(f"Stars today: {meta.get('stars_today')}")
    if "categories" in meta and meta.get("categories"):
        lines.append(f"Categories: {', '.join(meta.get('categories'))}")
    if "published_at" in meta:
        lines.append(f"Published at: {meta.get('published_at')}")

    return "\n".join(lines)


async def enrich_content_item(item: ContentItem) -> EnrichmentResult:
    """
    Enriches a single content item using an Agent with Tool Calling.
    If the item is a Hacker News discussion, the agent calls fetch_hn_discussion
    to inspect real developer opinions, debates, and warnings before finalizing.
    """
    base_llm = _get_base_llm(content_item_id=str(item.id))
    content_text = _build_content_text(item.raw_data or {})
    source = (item.raw_data or {}).get("source", "")
    meta = (item.raw_data or {}).get("metadata", {})

    # Guardrail 2: Sanitize and sandbox untrusted scraped web content
    safe_content_text, _ = sanitize_untrusted_scraped_data(content_text, source=source)

    # If item is from Hacker News, engage tool-calling agent
    is_hn = source == "hacker_news" or "id" in meta or "hn_url" in meta
    comments_count = meta.get("comments_count", 0)

    if is_hn and comments_count > 0:
        llm_with_tools = base_llm.bind_tools(AVAILABLE_TOOLS)

        agent_prompt = [
            SystemMessage(
                content=(
                    "You are an expert technical intelligence agent. Your job is to analyze developer news "
                    "and extract ground-truth technical insights. "
                    "For Hacker News items, you have the 'fetch_hn_discussion' tool. Use it to inspect "
                    "what the developer community thinks, including performance trade-offs, caveats, and practical feedback. "
                    "You also have 'search_hn_discussions' if you need context on past discussions about a tool."
                )
            ),
            HumanMessage(content=f"Item to analyze:\n\n{safe_content_text}"),
        ]

        try:
            # 1. Agent decides whether to call tools
            agent_msg = await llm_with_tools.ainvoke(agent_prompt)

            tool_messages: list[ToolMessage] = []
            if agent_msg.tool_calls:
                for tc in agent_msg.tool_calls:
                    tool_name = tc.get("name")
                    tool_args = tc.get("args", {})

                    # Guardrail 3: Validate tool arguments & boundaries
                    is_valid, sec_err = validate_tool_arguments(tool_name, tool_args)
                    if not is_valid:
                        log.warning("security.tool_argument_blocked", tool=tool_name, reason=sec_err)
                        tool_messages.append(
                            ToolMessage(content=f"Tool call blocked by security guardrail: {sec_err}", tool_call_id=tc["id"])
                        )
                        continue

                    log.info("enricher.agent_invoking_tool", tool=tool_name, args=tool_args, item=item.external_id)

                    tool_fn = TOOL_MAP.get(tool_name)
                    if tool_fn:
                        tool_res = await tool_fn.ainvoke(tool_args)
                        tool_messages.append(ToolMessage(content=str(tool_res), tool_call_id=tc["id"]))

            # 2. Synthesize with structured output schema
            structured_chain = base_llm.with_structured_output(EnrichmentResult)

            if tool_messages:
                full_conversation = agent_prompt + [agent_msg] + tool_messages
                full_conversation.append(
                    HumanMessage(content="Synthesize the analysis and tool findings into the required structured schema.")
                )
                return await structured_chain.ainvoke(full_conversation)

        except Exception as e:
            log.warning("enricher.tool_agent_failed_falling_back", error=str(e), item=item.external_id)

    # Standard / fallback direct structured extraction
    direct_chain = _STRUCTURED_PROMPT | base_llm.with_structured_output(EnrichmentResult)
    return await direct_chain.ainvoke({"content_text": content_text})


async def run_enrichment(batch_size: int = 50) -> dict[str, int]:
    """
    Processes one batch of scraped items using LangChain Agent with tool calling.
    Commits per item so a failure doesn't roll back the whole batch.
    """
    counts = {"processed": 0, "succeeded": 0, "failed": 0}
    sem = asyncio.Semaphore(5)

    with get_session() as session:
        # Emergency circuit-breaker: budget limit check
        if not is_within_budget(session):
            log.warning("enricher.aborted_budget_exceeded")
            return counts

        pending = (
            session.query(ContentItem)
            .filter(ContentItem.pipeline_status == PipelineStatus.SCRAPED)
            .limit(batch_size)
            .all()
        )

        if not pending:
            log.info("enricher.no_pending_items")
            return counts

        log.info("enricher.starting", count=len(pending))

        async def _process_single(item):
            async with sem:
                return await enrich_content_item(item)

        tasks = [_process_single(item) for item in pending]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for item, res in zip(pending, results):
            counts["processed"] += 1
            if isinstance(res, Exception):
                session.rollback()
                item.pipeline_status = PipelineStatus.FAILED
                item.failure_reason = f"enrichment_error: {res}"
                session.commit()
                counts["failed"] += 1
                log.error("enricher.item_failed", external_id=item.external_id, error=str(res))
                continue

            session.add(
                ContentEnrichment(
                    content_item_id=item.id,
                    title=res.title,
                    summary=res.summary,
                    tech_stack=res.tech_stack,
                    topics=res.topics,
                    use_case=res.use_case,
                    enriched_at=datetime.now(),
                    llm_model=ENRICHMENT_MODEL,
                )
            )
            item.pipeline_status = PipelineStatus.ENRICHED
            session.commit()
            counts["succeeded"] += 1
            log.info("enricher.item_done", external_id=item.external_id, title=res.title[:50])

    log.info("enricher.complete", **counts)
    return counts
