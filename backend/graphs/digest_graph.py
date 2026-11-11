# graphs/digest_graph.py
import asyncio
from datetime import date
from typing import Any, Dict, List, Literal, Optional
import uuid

from langgraph.graph import StateGraph, START, END
from sqlalchemy import text

from config import config
from graphs.state import UserDigestState
from services.digest_generator import generate_curated_digest
from services.mailer import build_digest_html, send_digest_email
from storage.db import SessionLocal as get_session
from storage.memory_store import (
    get_delivered_history_ids,
    get_memory_context_string,
    record_curated_digest,
)
from storage.models import UserProfile, UserEmbedding
from utils.logger import log


# ── Retrieval & Ranking Helpers ───────────────────────────────────────────────

def _get_candidate_items(session, user_embedding: list[float], limit: int = 60):
    query = text("""
        WITH ranked_candidates AS (
            SELECT
                ci.id, ci.external_id, ci.url, ci.raw_data,
                s.name AS source_name,
                ce.title, ce.summary, ce.tech_stack, ce.topics, ce.use_case,
                (cemb.embedding <=> CAST(:user_vec AS vector)) AS distance,
                ROW_NUMBER() OVER (
                    PARTITION BY 
                        CASE 
                            WHEN s.name ILIKE '%hacker%' OR s.name ILIKE '%hn%' OR ci.url ILIKE '%news.ycombinator.com%' THEN 'hn'
                            WHEN s.name ILIKE '%rss%' OR s.name ILIKE '%openai%' OR s.name ILIKE '%anthropic%' OR ci.url ILIKE '%openai.com%' OR ci.url ILIKE '%anthropic.com%' THEN 'rss'
                            ELSE 'github'
                        END
                    ORDER BY (cemb.embedding <=> CAST(:user_vec AS vector)) ASC
                ) as source_rank
            FROM content_items ci
            LEFT JOIN sources s ON s.id = ci.source_id
            JOIN content_enrichments ce ON ce.content_item_id = ci.id
            JOIN content_embeddings cemb ON cemb.content_item_id = ci.id
            WHERE ci.pipeline_status = 'EMBEDDED'
        )
        SELECT id, external_id, url, raw_data, source_name, title, summary, tech_stack, topics, use_case, distance
        FROM ranked_candidates
        WHERE source_rank <= 25
        ORDER BY distance ASC
        LIMIT :limit
    """)
    result = session.execute(query, {"user_vec": user_embedding, "limit": limit})
    return result.fetchall()


def _filter_disliked(candidates, disliked_tags: list[str], threshold: float = 0.5):
    if not disliked_tags:
        return candidates

    disliked_lower = {t.lower() for t in disliked_tags}
    filtered = []
    for row in candidates:
        item_tags = {t.lower() for t in (row.tech_stack or [])} | {t.lower() for t in (row.topics or [])}
        if not item_tags:
            filtered.append(row)
            continue
        overlap_count = len(item_tags & disliked_lower)
        overlap_ratio = overlap_count / len(item_tags)
        if overlap_ratio > threshold:
            continue
        filtered.append(row)
    return filtered


def classify_item_source(item: dict) -> str:
    """
    Classifies content into 3 distinct source categories:
    - 'github': GitHub Trending Repositories
    - 'rss': Official AI Lab News & RSS (OpenAI, Anthropic, AI blogs)
    - 'hn': Hacker News Community Debates & Discussions
    """
    src = str(item.get("source_name") or (item.get("raw_data") or {}).get("source") or "").strip().lower()
    url = str(item.get("url") or "").lower()
    ext_id = str(item.get("external_id") or "").lower()

    # 1. Hacker News
    if "hacker" in src or "hn" in src or "news.ycombinator.com" in url or ext_id.startswith("hn:"):
        return "hn"

    # 2. Official AI Lab / RSS News
    if any(k in src for k in ["rss", "openai", "anthropic", "feed"]):
        return "rss"
    if any(k in url for k in ["openai.com", "anthropic.com", "deepmind", "rss", "techcrunch", "arxiv"]):
        return "rss"

    # 3. GitHub Trending Repositories
    if "github" in src or "github.com" in url or ("/" in ext_id and not ext_id.startswith("http")):
        return "github"

    return "rss"


def _rank_items(candidates: list) -> list[dict]:
    """
    Ranks candidates purely by semantic relevance (cosine similarity).
    Zero star bias — repos and articles compete strictly on user relevance.
    """
    ranked = []
    for row in candidates:
        similarity_score = max(0.0, 1.0 - float(row.distance))
        ranked.append({
            **row._mapping,
            "final_score": similarity_score,
            "relevance_score": similarity_score,
        })
    return sorted(ranked, key=lambda x: x["final_score"], reverse=True)


def _balance_sources(
    ranked_items: list[dict],
    per_source_min: int = 2,
    per_source_max: int = 3,
    max_total: int = 8,
) -> list[dict]:
    """
    Guarantees balanced representation across ALL 3 sources in the email:
    - 2 to 3 items from GitHub Trending
    - 2 to 3 items from RSS Scraper News (OpenAI, Anthropic, AI news)
    - 2 to 3 items from Hacker News Community Debates
    """
    github_pool = []
    rss_pool = []
    hn_pool = []

    for it in ranked_items:
        stype = classify_item_source(it)
        if stype == "github":
            github_pool.append(it)
        elif stype == "rss":
            rss_pool.append(it)
        elif stype == "hn":
            hn_pool.append(it)

    # 1. First pass: reserve at least per_source_min (2) from each pool if available
    selected = []
    selected.extend(github_pool[:per_source_min])
    selected.extend(rss_pool[:per_source_min])
    selected.extend(hn_pool[:per_source_min])

    # 2. Second pass: allow up to per_source_max (3) from each pool based on user relevance
    extras = []
    if len(github_pool) > per_source_min:
        extras.extend(github_pool[per_source_min:per_source_max])
    if len(rss_pool) > per_source_min:
        extras.extend(rss_pool[per_source_min:per_source_max])
    if len(hn_pool) > per_source_min:
        extras.extend(hn_pool[per_source_min:per_source_max])

    extras.sort(key=lambda x: x.get("final_score", 0), reverse=True)

    for extra in extras:
        if len(selected) >= max_total:
            break
        selected.append(extra)

    # 3. If any pool was underpopulated, fill remaining up to at least 6 items
    if len(selected) < 6:
        seen_ids = {item.get("id") for item in selected}
        for item in ranked_items:
            if item.get("id") not in seen_ids:
                selected.append(item)
                seen_ids.add(item.get("id"))
                if len(selected) >= 6:
                    break

    # Return items sorted by user relevance score
    return sorted(selected, key=lambda x: x.get("final_score", 0), reverse=True)


def _build_templated_digest(name: Optional[str], liked_tags: List[str], ranked_items: List[dict]) -> dict:
    intro = f"Hey {name or 'there'} 👋, here's what's trending in {', '.join(liked_tags[:2]) or 'your areas'} today:"
    items = []
    for item in ranked_items:
        tech = item["tech_stack"][0] if item.get("tech_stack") else item.get("use_case", "tech")
        summary = item.get("summary") or ""
        one_liner = f"{summary[:120]}... (trending in {tech})"
        items.append({"external_id": item["external_id"], "one_liner": one_liner})
    return {"intro": intro, "items": items, "market_pulse": None, "security_alert": None}


# ── Graph Nodes ───────────────────────────────────────────────────────────────

def retrieve_candidates_node(state: UserDigestState) -> dict:
    """Retrieves semantic nearest-neighbor content items via pgvector."""
    user_embedding = state.get("user_embedding", [])
    if not user_embedding:
        return {"candidates": []}

    with get_session() as session:
        candidates = _get_candidate_items(session, user_embedding, limit=60)
        return {"candidates": candidates}


def filter_and_rank_node(state: UserDigestState) -> dict:
    """
    Filters disliked topics, applies long-term memory deduplication
    (excludes items delivered in the past 7 days), and ranks by similarity + popularity.
    """
    candidates = state.get("candidates", [])
    if not candidates:
        return {"ranked_items": []}

    user_id_str = state.get("user_id")
    delivered_history = set()
    if user_id_str:
        try:
            with get_session() as session:
                delivered_history = get_delivered_history_ids(session, uuid.UUID(user_id_str), days_window=7)
        except Exception as e:
            log.warning("graph.digest.memory_history_failed", error=str(e))

    # Exclude items already sent in the past 7 days (Memory Deduplication)
    if delivered_history:
        filtered_by_history = [c for c in candidates if str(getattr(c, "external_id", "")) not in delivered_history]
        if filtered_by_history:
            candidates = filtered_by_history

    disliked = state.get("disliked_tags", [])
    filtered = _filter_disliked(candidates, disliked)
    ranked = _rank_items(filtered)
    balanced_items = _balance_sources(ranked, per_source_min=2, per_source_max=3, max_total=8)
    return {"ranked_items": balanced_items}


def route_after_rank(state: UserDigestState) -> Literal["llm_digest_node", "templated_digest_node", "skip_delivery_node"]:
    """
    Conditional Edge:
    1. If no ranked candidates found -> skip delivery.
    2. If user requested 'Why it matters' insights -> route to Curator Agent.
    3. Else -> route to zero-cost templated generation.
    """
    if not state.get("ranked_items"):
        return "skip_delivery_node"
    if state.get("include_why_matters", True):
        return "llm_digest_node"
    return "templated_digest_node"


async def llm_digest_node(state: UserDigestState) -> dict:
    """
    Executes the Personal AI Curator Agent.
    Leverages long-term memory, checks security CVEs, fetches community consensus,
    and retrieves live AI market/token pricing before synthesizing the personalized digest.
    """
    ranked_items = state.get("ranked_items", [])
    user_id_str = state.get("user_id")
    user_uid = uuid.UUID(user_id_str) if user_id_str else None

    # Retrieve Long-Term Memory context
    memory_context = ""
    if user_uid:
        try:
            with get_session() as session:
                memory_context = get_memory_context_string(session, user_uid)
        except Exception as e:
            log.warning("graph.digest.memory_context_failed", error=str(e))

    try:
        curated_result = await generate_curated_digest(
            user_name=state.get("user_name"),
            liked_tags=state.get("liked_tags", []),
            disliked_tags=state.get("disliked_tags", []),
            custom_interests=state.get("custom_interests"),
            keyword_alerts=state.get("keyword_alerts"),
            memory_context=memory_context,
            ranked_items=ranked_items,
        )

        # Update UserMemory with newly curated items and agent continuity notes
        if user_uid:
            try:
                with get_session() as session:
                    record_curated_digest(
                        session=session,
                        user_id=user_uid,
                        delivered_items=ranked_items,
                        agent_note_update=curated_result.get("agent_memory_note"),
                    )
            except Exception as e:
                log.warning("graph.digest.memory_record_failed", error=str(e))

        return {
            "digest": curated_result,
            "market_pulse": curated_result.get("market_pulse"),
            "security_alert": curated_result.get("security_alert"),
        }

    except Exception as e:
        log.error("graph.digest.curator_agent_failed_fallback", user_id=user_id_str, error=str(e))
        digest = _build_templated_digest(state.get("user_name"), state.get("liked_tags", []), ranked_items)
        return {"digest": digest}


def templated_digest_node(state: UserDigestState) -> dict:
    """Zero-LLM-cost path: constructs summary directly from pre-computed enrichment."""
    digest = _build_templated_digest(
        state.get("user_name"),
        state.get("liked_tags", []),
        state.get("ranked_items", []),
    )
    return {"digest": digest}


def send_email_node(state: UserDigestState) -> dict:
    """Renders HTML email template with Security & Market Pulse widgets and delivers via Brevo."""
    user_email = state.get("user_email")
    digest = state.get("digest")
    ranked = state.get("ranked_items", [])

    if not digest or not user_email:
        return {"email_sent": False, "error": "missing_digest_or_email"}

    try:
        html = build_digest_html(
            user_name=state.get("user_name"),
            digest=digest,
            ranked_items=ranked,
            market_pulse=state.get("market_pulse") or digest.get("market_pulse"),
            security_alert=state.get("security_alert") or digest.get("security_alert"),
        )
        today_label = date.today().strftime("%b %d")
        sent = send_digest_email(user_email, f"⚡ StackPulse · {today_label} Developer Intelligence", html)
        return {"email_html": html, "email_sent": sent}
    except Exception as e:
        log.error("graph.digest.send_email_failed", email=user_email, error=str(e))
        return {"email_sent": False, "error": str(e)}


def skip_delivery_node(state: UserDigestState) -> dict:
    """Invoked when no candidate content is available for the user."""
    log.info("graph.digest.skipped", user_email=state.get("user_email"), reason="no_candidates")
    return {"email_sent": False, "error": "no_candidates_found"}


# ── Graph Builder ─────────────────────────────────────────────────────────────

def build_digest_graph():
    builder = StateGraph(UserDigestState)

    builder.add_node("retrieve_candidates_node", retrieve_candidates_node)
    builder.add_node("filter_and_rank_node", filter_and_rank_node)
    builder.add_node("llm_digest_node", llm_digest_node)
    builder.add_node("templated_digest_node", templated_digest_node)
    builder.add_node("send_email_node", send_email_node)
    builder.add_node("skip_delivery_node", skip_delivery_node)

    # Connections
    builder.add_edge(START, "retrieve_candidates_node")
    builder.add_edge("retrieve_candidates_node", "filter_and_rank_node")

    # Conditional routing after ranking
    builder.add_conditional_edges(
        "filter_and_rank_node",
        route_after_rank,
        {
            "llm_digest_node": "llm_digest_node",
            "templated_digest_node": "templated_digest_node",
            "skip_delivery_node": "skip_delivery_node",
        },
    )

    builder.add_edge("llm_digest_node", "send_email_node")
    builder.add_edge("templated_digest_node", "send_email_node")
    builder.add_edge("send_email_node", END)
    builder.add_edge("skip_delivery_node", END)

    return builder.compile()


digest_graph = build_digest_graph()


# ── Pipeline Runner Function ──────────────────────────────────────────────────

async def run_digest_pipeline_graph(top_n: int = 5) -> dict[str, int]:
    """Iterates through all embedded users and executes the LangGraph digest workflow."""
    counts = {"processed": 0, "sent": 0, "failed": 0, "skipped": 0}

    with get_session() as session:
        users = (
            session.query(UserProfile)
            .filter(UserProfile.is_active == True, UserProfile.embedding_status == "embedded")
            .all()
        )

        for user in users:
            counts["processed"] += 1
            user_emb = (
                session.query(UserEmbedding)
                .filter(UserEmbedding.user_id == user.id)
                .order_by(UserEmbedding.created_at.desc())
                .first()
            )
            if not user_emb:
                counts["skipped"] += 1
                continue

            user_state: UserDigestState = {
                "user_id": str(user.id),
                "user_name": user.name,
                "user_email": user.email,
                "user_embedding": user_emb.embedding.tolist(),
                "liked_tags": user.liked_tags or [],
                "disliked_tags": user.disliked_tags or [],
                "custom_interests": user.custom_interests or "",
                "keyword_alerts": user.keyword_alerts or "",
                "include_why_matters": bool(user.include_why_matters),
                "candidates": [],
                "ranked_items": [],
            }

            try:
                result = await digest_graph.ainvoke(user_state)
                if result.get("email_sent"):
                    counts["sent"] += 1
                elif result.get("error") == "no_candidates_found":
                    counts["skipped"] += 1
                else:
                    counts["failed"] += 1
            except Exception as e:
                counts["failed"] += 1
                log.error("graph.digest.user_execution_error", user=user.email, error=str(e))

    log.info("graph.digest.run_complete", **counts)
    return counts


if __name__ == "__main__":
    asyncio.run(run_digest_pipeline_graph())
