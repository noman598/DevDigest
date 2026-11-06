from datetime import datetime
from typing import List, Optional

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from config import config
from storage.db import SessionLocal as get_session
from storage.models import ContentEmbedding, ContentEnrichment, ContentItem, PipelineStatus
from utils.logger import log


def get_embedding_model(task_type: str = "retrieval_document") -> GoogleGenerativeAIEmbeddings:
    """Returns a LangChain Google GenAI embeddings instance pinned to 1536 dimensions."""
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=config.GEMINI_API_KEY,
        output_dimensionality=1536,
        task_type=task_type,
    )


def build_embedded_text(e: ContentEnrichment) -> str:
    parts = []
    if e.title:
        parts.append(f"Title: {e.title}")
    if e.summary:
        parts.append(f"Summary: {e.summary}")
    if e.tech_stack:
        parts.append(f"Tech stack: {', '.join(e.tech_stack)}")
    if e.topics:
        parts.append(f"Topics: {', '.join(e.topics)}")
    if e.use_case:
        parts.append(f"Use case: {e.use_case}")
    return "\n".join(parts)


def get_embedding(text: str) -> List[float]:
    """Generates embedding vector for a single document text using LangChain."""
    embedder = get_embedding_model(task_type="retrieval_document")
    return embedder.embed_query(text)


def run_embedding(batch_size: int = 50) -> dict[str, int]:
    """
    Process one batch of enriched items using LangChain Embeddings.
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
        embedder = get_embedding_model(task_type="retrieval_document")

        for item in pending:
            counts["processed"] += 1
            try:
                embedded_text = build_embedded_text(item.enrichment)
                vector = embedder.embed_query(embedded_text)

                session.add(
                    ContentEmbedding(
                        content_item_id=item.id,
                        embedding=vector,
                        embedding_model="Google-GenAI-LangChain",
                        embedded_text=embedded_text,
                        created_at=datetime.now(),
                    )
                )
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
