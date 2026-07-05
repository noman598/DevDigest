import json
from datetime import datetime

import anthropic

from backend.config import config
from backend.storage.db import get_session
from backend.storage.models import ContentEnrichment, ContentItem, PipelineStatus
from backend.utils.logger import log

_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# Haiku: cheap + fast for structured extraction. Swap to Sonnet if quality isn't enough.
ENRICHMENT_MODEL = "claude-haiku-4-5-20251001"

_PROMPT = """You are a technical content analyst. Given GitHub repository metadata, extract structured information.

Respond ONLY with a valid JSON object — no markdown, no explanation, no code fences.

Schema:
{{
  "title": "clean readable repository name",
  "summary": "2-3 sentence summary of what this does and who it is for",
  "tech_stack": ["array", "of", "specific", "technologies"],
  "topics": ["broad", "topic", "categories"],
  "use_case": "one of: library | tool | tutorial | research | framework | dataset | other"
}}

Repository data:
{repo_data}"""


def _build_repo_text(raw: dict) -> str:
    """Produce a clean, token-efficient text block from raw scraped data."""
    lines = []
    for key in ("name", "description", "language"):
        if raw.get(key):
            lines.append(f"{key.capitalize()}: {raw[key]}")
    if raw.get("topics"):
        lines.append(f"Topics: {', '.join(raw['topics'])}")
    if raw.get("stars"):
        lines.append(f"Stars: {raw['stars']}")
    if raw.get("readme"):
        lines.append(f"README (truncated):\n{raw['readme'][:3000]}")
    return "\n".join(lines)


def _call_llm(repo_text: str) -> dict:
    response = _client.messages.create(
        model=ENRICHMENT_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": _PROMPT.format(repo_data=repo_text)}],
    )
    return json.loads(response.content[0].text.strip())


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
                enriched = _call_llm(_build_repo_text(item.raw_data))

                session.add(ContentEnrichment(
                    content_item_id = item.id,
                    title           = enriched.get("title"),
                    summary         = enriched.get("summary"),
                    tech_stack      = enriched.get("tech_stack", []),
                    topics          = enriched.get("topics", []),
                    use_case        = enriched.get("use_case"),
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