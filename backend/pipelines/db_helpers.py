import uuid
from datetime import datetime
from dataclasses import asdict, is_dataclass
from typing import Any, List, Optional
from sqlalchemy.dialects.postgresql import insert

from storage.db import SessionLocal as get_session
from storage.models import ContentItem, IngestionRun, PipelineStatus, Source
from utils.logger import log
from scrapers.base import RawItem


def get_or_create_source(name: str) -> uuid.UUID:
    """Returns the UUID for a source name, creating it if it doesn't exist."""
    with get_session() as session:
        source = session.query(Source).filter_by(name=name).first()
        if not source:
            source = Source(id=uuid.uuid4(), name=name)
            session.add(source)
            session.commit()
            log.info("db_helpers.source_created", name=name)
            return source.id
        return source.id


def start_ingestion_run(source_id: uuid.UUID) -> IngestionRun:
    with get_session() as session:
        run = IngestionRun(
            source_id=source_id,
            started_at=datetime.now(),
            status="running",
        )
        session.add(run)
        session.commit()
        log.info("db_helpers.run_started", run_id=str(run.id))
        return run


def finish_ingestion_run(
    run_id: uuid.UUID,
    status: str,
    items_scraped: int = 0,
    items_new: int = 0,
    items_enriched: int = 0,
    items_embedded: int = 0,
    error_log: Optional[str] = None,
) -> None:
    with get_session() as session:
        run = session.query(IngestionRun).filter_by(id=run_id).first()
        if not run:
            log.warning("db_helpers.run_not_found", run_id=str(run_id))
            return
        run.status = status
        run.finished_at = datetime.now()
        run.items_scraped = items_scraped
        run.items_new = items_new
        run.items_enriched = items_enriched
        run.items_embedded = items_embedded
        run.error_log = error_log
        session.commit()
        log.info("db_helpers.run_finished", run_id=str(run_id), status=status)


def save_items_deduped(raw_items: List[Any], default_source_id: Optional[uuid.UUID] = None) -> int:
    """
    Bulk insert items across multiple sources (GitHub, OpenAI, Anthropic, etc.).
    Maps each item to its respective source_id and skips duplicates via uq_source_external.
    Returns the count of actually new rows inserted.
    """
    if not raw_items:
        return 0

    source_cache: dict[str, uuid.UUID] = {}

    rows = []
    for item in raw_items:
        item_source_name = getattr(item, "source", None) or "base"

        # Lookup or create source ID per item source
        if item_source_name not in source_cache:
            source_cache[item_source_name] = get_or_create_source(item_source_name)
        item_source_id = source_cache[item_source_name]

        # Determine external_id: prefer guid or url for news articles; repo name for github
        metadata = getattr(item, "metadata", {}) or {}
        if isinstance(metadata, dict) and metadata.get("guid"):
            external_id = str(metadata["guid"])
        elif item_source_name != "github_trending" and getattr(item, "url", None):
            external_id = item.url
        else:
            external_id = item.title

        # Convert RawItem to dict payload
        if is_dataclass(item):
            raw_payload = asdict(item)
        elif isinstance(item, dict):
            raw_payload = item
        else:
            raw_payload = {
                "source": item_source_name,
                "title": getattr(item, "title", ""),
                "url": getattr(item, "url", ""),
                "description": getattr(item, "description", ""),
                "metadata": metadata,
            }

        rows.append({
            "id": uuid.uuid4(),
            "source_id": item_source_id,
            "external_id": external_id,
            "url": getattr(item, "url", ""),
            "raw_data": raw_payload,
            "scraped_at": datetime.now(),
            "pipeline_status": PipelineStatus.SCRAPED,
            "created_at": datetime.now(),
        })

    with get_session() as session:
        stmt = (
            insert(ContentItem)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_source_external")
        )
        result = session.execute(stmt)
        session.commit()
        new_count = result.rowcount
        log.info("db_helpers.dedup_insert", total=len(rows), new=new_count)
        return new_count
