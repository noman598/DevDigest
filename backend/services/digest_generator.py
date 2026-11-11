# backend/services/digest_generator.py
from typing import Any, Dict, List, Optional
import asyncio

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from config import config
from security.guardrails import scan_direct_prompt_injection, validate_tool_arguments
from services.llm import BudgetUsageCallback
from tools.cve_tools import check_cve_vulnerabilities
from tools.github_tools import inspect_github_repo
from tools.hn_tools import fetch_hn_discussion
from tools.market_tools import get_ai_market_pulse
from utils.logger import log

DIGEST_MODEL = getattr(config, "GEMINI_MODEL", "gemini-3.5-flash-lite")

# Tools available to the Curator Agent
CURATOR_TOOLS = [
    get_ai_market_pulse,
    check_cve_vulnerabilities,
    fetch_hn_discussion,
    inspect_github_repo,
]
CURATOR_TOOL_MAP = {t.name: t for t in CURATOR_TOOLS}


class DigestItem(BaseModel):
    external_id: str = Field(description="content external_id, copied exactly as given")
    one_liner: str = Field(description="punchy 1-sentence explanation of why this matters specifically to this user")


class CuratorDigestResult(BaseModel):
    intro: str = Field(description="1-2 sentence personalized intro, maintaining continuity with past context if applicable")
    market_pulse: Optional[str] = Field(
        default=None,
        description="2-line AI model token rates / tech stock barometer if relevant to user interests"
    )
    security_alert: Optional[str] = Field(
        default=None,
        description="High or critical CVE advisory if discovered for any item in user's stack"
    )
    items: List[DigestItem]
    agent_memory_note: Optional[str] = Field(
        default=None,
        description="A 1-sentence note for tomorrow's memory summarizing the user's current focus"
    )


def _get_base_llm():
    callbacks = [
        BudgetUsageCallback(
            operation="digest_generation",
            provider="gemini",
        )
    ]
    return ChatGoogleGenerativeAI(
        model=DIGEST_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0.2,
        max_output_tokens=2048,
        callbacks=callbacks,
    )


def _item_source_label(item: Dict[str, Any]) -> str:
    src = str(item.get("source_name") or (item.get("raw_data") or {}).get("source") or "").lower()
    url = str(item.get("url") or "").lower()
    ext_id = str(item.get("external_id") or "").lower()
    if "hacker" in src or "hn" in src or "news.ycombinator.com" in url or ext_id.startswith("hn:"):
        return "Hacker News Discussion"
    if "openai" in src or "openai.com" in url:
        return "OpenAI Official News"
    if "anthropic" in src or "anthropic.com" in url:
        return "Anthropic Official News"
    if "rss" in src or any(k in url for k in ["techcrunch", "arxiv", "feed"]):
        return "AI News / Research"
    return "GitHub Trending Repo"


async def generate_curated_digest(
    user_name: Optional[str],
    liked_tags: List[str],
    disliked_tags: List[str],
    custom_interests: Optional[str],
    keyword_alerts: Optional[str],
    memory_context: str,
    ranked_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Curates a personalized digest using an Autonomous Agent with Tools and Memory.
    The agent inspects community reaction, verifies security status, and retrieves
    live market/token pricing before synthesizing the final output.
    """
    base_llm = _get_base_llm()
    llm_with_tools = base_llm.bind_tools(CURATOR_TOOLS)

    items_text = "\n".join(
        f"[{idx}] (ID: {item.get('external_id')}) [{_item_source_label(item)}]\n"
        f"    Title: {item.get('title')}\n"
        f"    Summary: {item.get('summary')}\n"
        f"    Tech: {', '.join(item.get('tech_stack', []))}\n"
        f"    Topics: {', '.join(item.get('topics', []))}"
        for idx, item in enumerate(ranked_items, 1)
    )

    # Guardrail 1: Sanitize direct user inputs against prompt injection
    safe_interests = scan_direct_prompt_injection(custom_interests).sanitized_input if custom_interests else "None"
    safe_alerts = scan_direct_prompt_injection(keyword_alerts).sanitized_input if keyword_alerts else "None"

    user_info = (
        f"Subscriber: {user_name or 'Developer'}\n"
        f"Primary Tech Stack / Liked Topics: {', '.join(liked_tags) if liked_tags else 'General Tech'}\n"
        f"Custom Interests: {safe_interests}\n"
        f"Keyword Alerts: {safe_alerts}\n"
        f"Disliked Topics: {', '.join(disliked_tags) if disliked_tags else 'None'}\n\n"
        f"{memory_context}\n\n"
        f"Today's Top Matched Items:\n{items_text}"
    )

    agent_prompt = [
        SystemMessage(
            content=(
                "You are an elite Senior Technical Curator and Chief of Staff for developers. "
                "Your mission is to curate an engaging, hyper-personalized daily digest. "
                "You have access to tools:\n"
                "- 'get_ai_market_pulse': ALWAYS invoke this if the subscriber likes AI/ML, LLMs, or Startups to fetch today's token pricing shift and tech stocks.\n"
                "- 'check_cve_vulnerabilities': ALWAYS invoke this if any item in today's candidates or the subscriber's stack mentions an open-source library/framework (e.g. PyTorch, LangChain, FastAPI, Transformers, urllib3, or any package in candidate tech stack) to audit for active security CVE advisories.\n"
                "- 'fetch_hn_discussion': invoke this if an item is from Hacker News with comments to extract community consensus.\n"
                "- 'inspect_github_repo': invoke this if you need verified license or maintenance health for a GitHub repo.\n\n"
                "Be proactive in calling tools to enrich the digest (especially checking CVEs for open-source dependencies and market pulse) before synthesizing your findings."
            )
        ),
        HumanMessage(content=user_info),
    ]

    try:
        # Step 1: Agent decides tool calls
        agent_msg = await llm_with_tools.ainvoke(agent_prompt)

        tool_messages: list[ToolMessage] = []
        market_pulse_collected: Optional[str] = None
        security_alert_collected: Optional[str] = None

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

                log.info("curator_agent.invoking_tool", tool=tool_name, args=tool_args)

                tool_fn = CURATOR_TOOL_MAP.get(tool_name)
                if tool_fn:
                    tool_res = await tool_fn.ainvoke(tool_args)
                    res_str = str(tool_res)
                    tool_messages.append(ToolMessage(content=res_str, tool_call_id=tc["id"]))

                    # Cache special widget strings if tool returned them
                    if tool_name == "get_ai_market_pulse":
                        market_pulse_collected = res_str
                    elif tool_name == "check_cve_vulnerabilities" and "Security Advisory" in res_str:
                        security_alert_collected = res_str

        # Step 2: Synthesize structured output
        structured_chain = base_llm.with_structured_output(CuratorDigestResult)

        synth_instruction = HumanMessage(
            content=(
                "Synthesize the final personalized digest adhering strictly to the schema. "
                "CRITICAL REQUIREMENT: In 'items', you MUST include a DigestItem for EVERY single candidate item "
                "listed in 'Today's Top Matched Items' above (all items, without dropping or omitting any). "
                "Copy each item's 'external_id' exactly as given."
            )
        )

        if tool_messages:
            full_conv = agent_prompt + [agent_msg] + tool_messages + [synth_instruction]
            result: CuratorDigestResult = await structured_chain.ainvoke(full_conv)
        else:
            full_conv = agent_prompt + [synth_instruction]
            result = await structured_chain.ainvoke(full_conv)

        return {
            "intro": result.intro,
            "market_pulse": result.market_pulse or market_pulse_collected,
            "security_alert": result.security_alert or security_alert_collected,
            "items": [{"external_id": i.external_id, "one_liner": i.one_liner} for i in result.items],
            "agent_memory_note": result.agent_memory_note,
        }

    except Exception as e:
        log.warning("curator_agent.failed_falling_back", error=str(e))
        # Fallback to direct structured extraction
        fallback_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "Write a short personalized intro and a 1-sentence 'why this matters' for EVERY single item "
                "provided in user_info. Return a DigestItem for all items in the schema without dropping any.",
            ),
            ("human", "{user_info}"),
        ])
        fallback_chain = fallback_prompt | base_llm.with_structured_output(CuratorDigestResult)
        res = await fallback_chain.ainvoke({"user_info": user_info})
        return {
            "intro": res.intro,
            "market_pulse": None,
            "security_alert": None,
            "items": [{"external_id": i.external_id, "one_liner": i.one_liner} for i in res.items],
            "agent_memory_note": res.agent_memory_note,
        }
