from datetime import datetime

from openai import OpenAI

from backend.config import config
from backend.storage.db import get_session
from backend.storage.models import ContentEmbedding, ContentEnrichment, ContentItem, PipelineStatus
from backend.utils.logger import log

_client = OpenAI(api_key=config.OPENAI_API_KEY)

EMBEDDING_MODEL = "text-embedding-3-small"  # 1536 dims, matches Vector(1536) in models.py


def _build_embedded_text(e: ContentEnrichment) -> str:
    parts = []
    if e.title:      parts.append(f"Title: {e.title}")
    if e.summary:    parts.append(f"Summary: {e.summary}")
    if e.tech_stack: parts.append(f"Tech stack: {', '.join(e.tech_stack)}")
    if e.topics:     parts.append(f"Topics: {', '.join(e.topics)}")
    if e.use_case:   parts.append(f"Use case: {e.use_case}")
    return "\n".join(parts)


def _get_embedding(text: str) -> list[float]:
    response = _client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def run_embedding(batch_size: int = 100) -> dict[str, int]:
    """
    Process one batch of enriched items. Returns counts for the runner to log.
    Commits per item — idempotent on re-run.
    """
    counts = {"processed": 0, "succeeded": 0, "failed": 0}

    with get_session() as session:
        pending = (
            session.query(ContentItem)
            .join(ContentEnrichment, ContentItem.id == ContentEnrichment.content_item_id)
            .filter(ContentItem.pipeline_status == PipelineStatus.ENRICHED)
            .limit(batch_size)
            .all()
        )

        if not pending:
            log.info("embedder.no_pending_items")
            return counts

        log.info("embedder.starting", count=len(pending))

        for item in pending:
            counts["processed"] += 1
            try:
                embedded_text = _build_embedded_text(item.enrichment)
                vector = _get_embedding(embedded_text)

                session.add(ContentEmbedding(
                    content_item_id = item.id,
                    embedding       = vector,
                    embedding_model = EMBEDDING_MODEL,
                    embedded_text   = embedded_text,
                    created_at      = datetime.now,
                ))
                item.pipeline_status = PipelineStatus.EMBEDDED
                session.commit()
                counts["succeeded"] += 1
                log.info("embedder.item_done", external_id=item.external_id)

            except Exception as e:
                session.rollback()
                item.pipeline_status = PipelineStatus.FAILED
                item.failure_reason = f"embedding_error: {e}"
                session.commit()
                counts["failed"] += 1
                log.error("embedder.item_failed", external_id=item.external_id, error=str(e))

    log.info("embedder.complete", **counts)
    return counts