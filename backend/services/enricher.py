import json
from datetime import datetime
import instructor
from pydantic import BaseModel, Field
from groq import Groq
from typing import Literal
# import anthropic

from config import config
from storage.db import SessionLocal as get_session
from storage.models import ContentEnrichment, ContentItem, PipelineStatus
from utils.logger import log

_client = instructor.from_groq(Groq(api_key=config.GROQ_API_KEY), mode=instructor.Mode.JSON)
# Haiku: cheap + fast for structured extraction. Swap to Sonnet if quality isn't enough.
ENRICHMENT_MODEL = "llama-3.3-70b-versatile"

class EnrichmentResult(BaseModel):
    title: str = Field(description="clean readable repository name")
    summary: str = Field(description="2-3 sentence summary of what this does and who it's for")
    tech_stack: list[str] = Field(description="specific technologies/frameworks used")
    topics: list[str] = Field(description="broad topic categories")
    use_case: Literal["library", "tool", "tutorial", "research", "framework", "dataset", "other"]


# _PROMPT = """You are a technical content analyst. Given GitHub repository metadata, extract structured information.

# Respond ONLY with a valid JSON object — no markdown, no explanation, no code fences.

# Schema:
# {{
#   "title": "clean readable repository name",
#   "summary": "2-3 sentence summary of what this does and who it is for",
#   "tech_stack": ["array", "of", "specific", "technologies"],
#   "topics": ["broad", "topic", "categories"],
#   "use_case": "one of: library | tool | tutorial | research | framework | dataset | other"
# }}

# Repository data:
# {repo_data}"""


def _build_repo_text(raw: dict) -> str:
    """Matches actual scraped shape: {source, title, url, description, metadata:{language, stars_today, total_stars}}"""
    meta = raw.get("metadata", {})
    lines = [
        f"Repository: {raw.get('title')}",
        f"Description: {raw.get('description') or 'N/A'}",
        f"Language: {meta.get('language', 'Unknown')}",
        f"Total stars: {meta.get('total_stars', '0')}",
        f"Stars today: {meta.get('stars_today', '0')}",
    ]
    return "\n".join(lines)


def _call_llm(repo_text: str) -> dict:
    return _client.chat.completions.create(
        model=ENRICHMENT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": f"Analyze this GitHub repository:\n\n{repo_text}"}],
        response_model=EnrichmentResult,
    )


def run_enrichment(batch_size: int = 50) -> dict[str, int]:
    """
    Process one batch of scraped items. Returns counts for the runner to log.
    Commits per item so a crash doesn't roll back the whole batch.
    """
    counts = {"processed": 0, "succeeded": 0, "failed": 0}

    with get_session() as session:
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

        for item in pending:
            counts["processed"] += 1
            try:
                enriched = _call_llm(_build_repo_text(item.raw_data)) #Object Response

                session.add(ContentEnrichment(
                    content_item_id = item.id,
                    title           = enriched.title,
                    summary         = enriched.summary,
                    tech_stack      = enriched.tech_stack,
                    topics          = enriched.topics,
                    use_case        = enriched.use_case,
                    enriched_at     = datetime.now(),
                    llm_model       = ENRICHMENT_MODEL,
                ))
                item.pipeline_status = PipelineStatus.ENRICHED
                session.commit()
                counts["succeeded"] += 1
                log.info("enricher.item_done", external_id=item.external_id)

            except Exception as e:
                session.rollback()
                item.pipeline_status = PipelineStatus.FAILED
                item.failure_reason = f"enrichment_error: {e}"
                session.commit()
                counts["failed"] += 1
                log.error("enricher.item_failed", external_id=item.external_id, error=str(e))

    log.info("enricher.complete", **counts)
    return counts