# graphs/digest_graph.py
import asyncio
from typing import Any, Dict, List, Literal, Optional
import uuid

from langgraph.graph import StateGraph, START, END
from sqlalchemy import text

from config import config
from graphs.state import UserDigestState
from services.digest_generator import generate_batch_digest
from services.mailer import build_digest_html, send_digest_email
from storage.db import SessionLocal as get_session
from storage.models import UserProfile, UserEmbedding
from utils.logger import log


# ── Retrieval & Ranking Helpers ───────────────────────────────────────────────

def _get_candidate_items(session, user_embedding: list[float], limit: int = 40):
    query = text("""
        SELECT
            ci.id, ci.external_id, ci.url, ci.raw_data,
            ce.title, ce.summary, ce.tech_stack, ce.topics, ce.use_case,
            (cemb.embedding <=> CAST(:user_vec AS vector)) AS distance
        FROM content_items ci
        JOIN content_enrichments ce ON ce.content_item_id = ci.id
        JOIN content_embeddings cemb ON cemb.content_item_id = ci.id
        WHERE ci.pipeline_status = 'EMBEDDED'
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


def _rank_items(candidates, weight_similarity=0.7, weight_popularity=0.3):
    ranked = []
    for row in candidates:
        similarity_score = 1 - row.distance
        stars_today_raw = (row.raw_data or {}).get("metadata", {}).get("stars_today", "0")
        stars_today = int(str(stars_today_raw).replace(",", "") or 0)
        popularity_score = min(stars_today / 500, 1.0)
        final_score = (weight_similarity * similarity_score) + (weight_popularity * popularity_score)
        ranked.append({**row._mapping, "final_score": final_score})
    return sorted(ranked, key=lambda x: x["final_score"], reverse=True)


def _build_templated_digest(name: Optional[str], liked_tags: List[str], ranked_items: List[dict]) -> dict:
    intro = f"Hey {name or 'there'} 👋, here's what's trending in {', '.join(liked_tags[:2]) or 'your areas'} today:"
    items = []
    for item in ranked_items:
        tech = item["tech_stack"][0] if item.get("tech_stack") else item.get("use_case", "tech")
        summary = item.get("summary") or ""
        one_liner = f"{summary[:120]}... (trending in {tech})"
        items.append({"external_id": item["external_id"], "one_liner": one_liner})
    return {"intro": intro, "items": items}


# ── Graph Nodes ───────────────────────────────────────────────────────────────

def retrieve_candidates_node(state: UserDigestState) -> dict:
    """Retrieves semantic nearest-neighbor content items via pgvector."""
    user_embedding = state.get("user_embedding", [])
    if not user_embedding:
        return {"candidates": []}

    with get_session() as session:
        candidates = _get_candidate_items(session, user_embedding, limit=20)
        return {"candidates": candidates}


def filter_and_rank_node(state: UserDigestState) -> dict:
    """Filters disliked topics and ranks remaining items by similarity + popularity."""
    candidates = state.get("candidates", [])
    if not candidates:
        return {"ranked_items": []}

    disliked = state.get("disliked_tags", [])
    filtered = _filter_disliked(candidates, disliked)
    ranked = _rank_items(filtered)[:5]
    return {"ranked_items": ranked}


def route_after_rank(state: UserDigestState) -> Literal["llm_digest_node", "templated_digest_node", "skip_delivery_node"]:
    """
    Conditional Edge:
    1. If no ranked candidates found -> skip delivery.
    2. If user requested 'Why it matters' insights -> route to LLM generation.
    3. Else -> route to zero-cost templated generation.
    """
    if not state.get("ranked_items"):
        return "skip_delivery_node"
    if state.get("include_why_matters", True):
        return "llm_digest_node"
    return "templated_digest_node"


async def llm_digest_node(state: UserDigestState) -> dict:
    """Generates personalized commentary and intro via LangChain ChatGroq."""
    ranked_items = state.get("ranked_items", [])
    user_id = state.get("user_id")

    class _MockUser:
        def __init__(self, uid, liked, custom):
            self.id = uid
            self.liked_tags = liked
            self.custom_interests = custom

    user_obj = _MockUser(
        user_id,
        state.get("liked_tags", []),
        state.get("custom_interests", ""),
    )

    try:
        batch_digests = await generate_batch_digest([(user_obj, ranked_items)])
        digest = batch_digests.get(str(user_id))
        if not digest:
            digest = _build_templated_digest(state.get("user_name"), state.get("liked_tags", []), ranked_items)
        return {"digest": digest}
    except Exception as e:
        log.error("graph.digest.llm_failed_fallback", user_id=user_id, error=str(e))
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
    """Renders HTML email template and delivers via Brevo."""
    user_email = state.get("user_email")
    digest = state.get("digest")
    ranked = state.get("ranked_items", [])

    if not digest or not user_email:
        return {"email_sent": False, "error": "missing_digest_or_email"}

    try:
        html = build_digest_html(state.get("user_name"), digest, ranked)
        sent = send_digest_email(user_email, "Your DevSnack digest 🍿", html)
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
