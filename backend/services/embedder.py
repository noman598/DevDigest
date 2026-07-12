from datetime import datetime

# from openai import OpenAI

from config import config
from storage.db import SessionLocal as get_session
from storage.models import ContentEmbedding, ContentEnrichment, ContentItem, PipelineStatus
from utils.logger import log
from google import genai
from google.genai.types import EmbedContentConfig

# import cohere
# _client = OpenAI(api_key=config.OPENAI_API_KEY)

# EMBEDDING_MODEL = "text-embedding-3-small"  # 1536 dims, matches Vector(1536) in models.py


def _build_embedded_text(e: ContentEnrichment) -> str:
    parts = []
    if e.title:      parts.append(f"Title: {e.title}")
    if e.summary:    parts.append(f"Summary: {e.summary}")
    if e.tech_stack: parts.append(f"Tech stack: {', '.join(e.tech_stack)}")
    if e.topics:     parts.append(f"Topics: {', '.join(e.topics)}")
    if e.use_case:   parts.append(f"Use case: {e.use_case}")
    return "\n".join(parts)


# def _get_embedding(text: str) -> list[float]:
#     response = _client.embeddings.create(model=EMBEDDING_MODEL, input=text)
#     return response.data[0].embedding

def _get_embedding(text: str):
    # co = cohere.ClientV2(api_key=config.COHERE_API_KEY)

    # # text_inputs = [
    # #     {
    # #         "content": [
    # #             {"type": "text", "text": "hello"},
    # #             {"type": "text", "text": "goodbye"}
    # #         ]
    # #     },
    # # ]

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



def run_embedding(batch_size: int = 50) -> dict[str, int]:
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
                    embedding_model = 'Google-GenAI',
                    embedded_text   = embedded_text,
                    created_at      = datetime.now(),
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