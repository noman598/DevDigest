"""
Embeds user profiles into vectors for personalization matching.
Uses LangChain Google GenAI Embeddings pinned to 1536 dimensions.
"""
from datetime import datetime

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import config
from storage.db import SessionLocal as get_session
from storage.models import UserProfile, UserEmbedding
from utils.logger import log


def _get_embedder() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=config.GEMINI_API_KEY,
        output_dimensionality=1536,
        task_type="retrieval_query",
    )


def _build_profile_text(user: UserProfile) -> str:
    """Flatten preferences into one text block."""
    parts = [
        f"Interested in: {', '.join(user.liked_tags or [])}",
        f"Not interested in: {', '.join(user.disliked_tags or [])}",
        user.custom_interests or "",
        f"Keywords to watch: {user.keyword_alerts}" if user.keyword_alerts else "",
    ]
    return "\n".join(p for p in parts if p)


def run_user_embedding(batch_size: int = 50) -> dict[str, int]:
    counts = {"processed": 0, "succeeded": 0, "failed": 0}
    embedder = _get_embedder()

    with get_session() as session:
        pending = (
            session.query(UserProfile)
            .filter(UserProfile.embedding_status == "pending")
            .limit(batch_size)
            .all()
        )

        if not pending:
            log.info("user_embedder.no_pending_users")
            return counts

        log.info("user_embedder.starting", count=len(pending))

        for user in pending:
            counts["processed"] += 1
            try:
                text = _build_profile_text(user)
                vector = embedder.embed_query(text)

                existing = (
                    session.query(UserEmbedding)
                    .filter(
                        UserEmbedding.user_id == user.id,
                        UserEmbedding.embedding_model == "Google-GenAI-LangChain",
                    )
                    .first()
                )
                if existing:
                    existing.embedding = vector
                    existing.embedded_text = text
                    existing.created_at = datetime.now()
                else:
                    session.add(
                        UserEmbedding(
                            user_id=user.id,
                            embedding=vector,
                            embedding_model="Google-GenAI-LangChain",
                            embedded_text=text,
                        )
                    )
                user.embedding_status = "embedded"
                session.commit()
                counts["succeeded"] += 1
                log.info("user_embedder.user_done", email=user.email)

            except Exception as e:
                session.rollback()
                user.embedding_status = "failed"
                session.commit()
                counts["failed"] += 1
                log.error("user_embedder.user_failed", email=user.email, error=str(e))

    log.info("user_embedder.complete", **counts)
    return counts
