from datetime import datetime
from typing import Literal, Optional
import asyncio

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from config import config
from services.llm import BudgetUsageCallback, is_within_budget
from storage.db import SessionLocal as get_session
from storage.models import ContentEnrichment, ContentItem, PipelineStatus
from utils.logger import log

ENRICHMENT_MODEL = "qwen/qwen3.8-27b"


class EnrichmentResult(BaseModel):
    title: str = Field(description="clean readable repository or article title")
    summary: str = Field(description="2-3 sentence summary of what this does, who it's for, and why it matters")
    tech_stack: list[str] = Field(default=[], description="specific technologies/frameworks used or mentioned")
    topics: list[str] = Field(default=[], description="broad topic categories (e.g. AI/ML, DevOps, LLMs)")
    use_case: Literal["library", "tool", "tutorial", "research", "framework", "dataset", "announcement", "other"] = Field(
        description="primary classification of the content"
    )


# LangChain Prompt Template
_ENRICHMENT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are an expert technical content analyst. Analyze the following developer content "
        "and extract accurate, structured metadata.",
    ),
    ("human", "Content item to analyze:\n\n{content_text}"),
])


def _get_llm(content_item_id: Optional[str] = None):
    callbacks = [
        BudgetUsageCallback(
            operation="enrichment",
            provider="groq",
            content_item_id=content_item_id,
        )
    ]
    llm = ChatGroq(
        model=ENRICHMENT_MODEL,
        api_key=config.GROQ_API_KEY,
        temperature=0.1,
        max_tokens=1024,
        callbacks=callbacks,
    )
    return _ENRICHMENT_PROMPT | llm.with_structured_output(EnrichmentResult)


def _build_content_text(raw: dict) -> str:
    """Formats raw item data whether it is from GitHub or an RSS/News source."""
    source = raw.get("source", "")
    title = raw.get("title", "")
    desc = raw.get("description") or "N/A"
    meta = raw.get("metadata", {})

    lines = [
        f"Source: {source}",
        f"Title: {title}",
        f"Description: {desc}",
    ]

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
    """Enriches a single content item using LangChain ChatGroq."""
    chain = _get_llm(content_item_id=str(item.id))
    content_text = _build_content_text(item.raw_data or {})
    return await chain.ainvoke({"content_text": content_text})


async def run_enrichment(batch_size: int = 50) -> dict[str, int]:
    """
    Processes one batch of scraped items using LangChain.
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
            log.info("enricher.item_done", external_id=item.external_id)

    log.info("enricher.complete", **counts)
    return counts
