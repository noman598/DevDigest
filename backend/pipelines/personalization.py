# pipeline/personalization.py

from sqlalchemy import text

from storage.db import SessionLocal as get_session
from storage.models import UserProfile, UserEmbedding
from services.digest_generator import generate_batch_digest
from services.mailer import build_digest_html, send_digest_email
from utils.logger import log

LLM_BATCH_SIZE = 15


def get_candidate_items(session, user_embedding: list[float], limit: int = 40, hours: int = 48):
    query = text(f"""
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
    #  AND ci.scraped_at >= NOW() - INTERVAL '{hours} hours'
    result = session.execute(query, {"user_vec": user_embedding, "limit": limit})
    return result.fetchall()


def filter_disliked(candidates, disliked_tags: list[str],threshold: float = 0.5):
    """Hard-exclude any item whose tech_stack or topics overlap with disliked_tags."""
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

def rank_items(candidates, weight_similarity=0.7, weight_popularity=0.3):
    ranked = []
    for row in candidates:
        similarity_score = 1 - row.distance
        stars_today_raw = row.raw_data.get("metadata", {}).get("stars_today", "0")
        stars_today = int(str(stars_today_raw).replace(",", "") or 0)
        popularity_score = min(stars_today / 500, 1.0)
        final_score = (weight_similarity * similarity_score) + (weight_popularity * popularity_score)
        ranked.append({**row._mapping, "final_score": final_score})
    return sorted(ranked, key=lambda x: x["final_score"], reverse=True)


def build_templated_digest(user: UserProfile, ranked_items: list[dict]) -> dict:
    """Zero-LLM-cost path — reuses enrichment summary/tech_stack already generated in Flow 1."""
    intro = f"Hey {user.name or 'there'} 👋, here's what's trending in {', '.join(user.liked_tags[:2]) or 'your areas'} today:"
    items = []
    for item in ranked_items:
        tech = item["tech_stack"][0] if item["tech_stack"] else item.get("use_case", "dev")
        one_liner = f"{item['summary'][:120]}... (trending in {tech})"
        items.append({"external_id": item["external_id"], "one_liner": one_liner})
    return {"intro": intro, "items": items}


def get_user_candidates(session, user: UserProfile, top_n: int = 5):
    """Shared step for both paths: fetch + rank candidates for one user."""
    user_emb = (
        session.query(UserEmbedding)
        .filter(UserEmbedding.user_id == user.id)
        .order_by(UserEmbedding.created_at.desc())
        .first()
    )
    if not user_emb:
        return None

    candidates = get_candidate_items(session, user_emb.embedding.tolist(), limit=5)
    if not candidates:
        return None
    candidates = filter_disliked(candidates, user.disliked_tags)
    return rank_items(candidates)[:5]


def run_digest_pipeline(top_n: int = 5) -> dict[str, int]:
    counts = {"processed": 0, "sent": 0, "failed": 0, "skipped": 0, "llm_calls_made": 0}

    with get_session() as session:
        users = (
            session.query(UserProfile)
            .filter(UserProfile.is_active == True, UserProfile.embedding_status == "embedded")
            .all()
        )

        templated_queue: list[tuple[UserProfile, list[dict]]] = []
        llm_queue: list[tuple[UserProfile, list[dict]]] = []

        # ── Pass 1: cheap, deterministic — fetch + rank candidates for everyone ──
        for user in users:
            counts["processed"] += 1
            ranked = get_user_candidates(session, user, top_n)
            if not ranked:
                counts["skipped"] += 1
                continue

            if user.include_why_matters:
                llm_queue.append((user, ranked))
            else:
                templated_queue.append((user, ranked))

        log.info("digest.pass1_done", templated=len(templated_queue), llm_opted_in=len(llm_queue))

        # ── Pass 2a: templated path — zero LLM cost ──
        for user, ranked in templated_queue:
            try:
                digest = build_templated_digest(user, ranked)
                html = build_digest_html(user.name, digest, ranked)
                sent = send_digest_email(user.email, "Your DevSnack digest 🍿", html)
                counts["sent" if sent else "failed"] += 1
            except Exception as e:
                counts["failed"] += 1
                log.error("digest.templated_failed", email=user.email, error=str(e))

        # ── Pass 2b: LLM path — batched across users, not one call per user ──
        for i in range(0, len(llm_queue), LLM_BATCH_SIZE):
            batch = llm_queue[i : i + LLM_BATCH_SIZE]
            try:
                batch_digests = generate_batch_digest(batch)
                counts["llm_calls_made"] += 1

                for user, ranked in batch:
                    digest = batch_digests.get(str(user.id))
                    if not digest:
                        counts["failed"] += 1
                        continue
                    html = build_digest_html(user.name, digest, ranked)
                    sent = send_digest_email(user.email, "Your DevSnack digest 🍿", html)
                    counts["sent" if sent else "failed"] += 1

            except Exception as e:
                # Fallback: whole LLM batch failed (provider down/rate limited) ->
                # degrade to templated digests for this batch instead of losing the emails entirely
                log.error("digest.llm_batch_failed_fallback_to_templated", error=str(e), batch_size=len(batch))
                for user, ranked in batch:
                    try:
                        digest = build_templated_digest(user, ranked)
                        html = build_digest_html(user.name, digest, ranked)
                        sent = send_digest_email(user.email, "Your DevSnack digest 🍿", html)
                        counts["sent" if sent else "failed"] += 1
                    except Exception as inner_e:
                        counts["failed"] += 1
                        log.error("digest.fallback_failed", email=user.email, error=str(inner_e))

    log.info("digest.complete", **counts)
    return counts


if __name__ == "__main__":
    run_digest_pipeline()