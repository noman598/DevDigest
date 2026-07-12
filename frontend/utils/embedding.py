"""
Embeds user profiles into vectors for personalization matching.
Mirrors services/embedder.py's pattern — reuses the same Cohere embedding call.
"""
from datetime import datetime

from storage.db import SessionLocal as get_session
from storage.models import UserProfile, UserEmbedding
from utils.logger import log
# import cohere
from config import config
from google import genai
from google.genai.types import EmbedContentConfig

def _build_profile_text(user: UserProfile) -> str:
    """Flatten preferences into one text block — same idea as _build_embedding_text for content."""
    parts = [
        f"Interested in: {', '.join(user.liked_tags or [])}",
        f"Not interested in: {', '.join(user.disliked_tags or [])}",
        user.custom_interests or "",
        f"Keywords to watch: {user.keyword_alerts}" if user.keyword_alerts else "",
    ]
    return "\n".join(p for p in parts if p)

def _get_embedding(text: str):
    # co = cohere.ClientV2(api_key=config.COHERE_API_KEY)

    # text_inputs = [
    #     {
    #         "content": [
    #             {"type": "text", "text": "hello"},
    #             {"type": "text", "text": "goodbye"}
    #         ]
    #     },
    # ]

    # response = co.embed(
    #     texts=[text],
    #     model="embed-v4.0",
    #     input_type="search_document",
    #     embedding_types=["float"],
    # )
    # print(response)
    # return response.embeddings.float[0]


    client = genai.Client(api_key=config.GEMINI_API_KEY)

    result = client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
            config=EmbedContentConfig(
        task_type="RETRIEVAL_DOCUMENT",   # or RETRIEVAL_QUERY for user profile side
        output_dimensionality=1536,       # explicitly pin it — don't rely on the 3072 default
    ),
    )

    print(result.embeddings)
    vector = result.embeddings[0].values   # <-- extract the actual float list
    return vector

def run_user_embedding(batch_size: int = 50) -> dict[str, int]:
    counts = {"processed": 0, "succeeded": 0, "failed": 0}

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
                vector = _get_embedding(text)

                session.add(UserEmbedding(
                    user_id         = user.id,
                    embedding       = vector,
                    embedding_model = 'Cohere',
                    embedded_text   = text,
                ))
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