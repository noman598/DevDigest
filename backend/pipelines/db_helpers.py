import uuid
from datetime import datetime
from dataclasses import asdict
from typing import List
from sqlalchemy.dialects.postgresql import insert

from storage.db import SessionLocal as get_session
from storage.models import ContentItem, IngestionRun, PipelineStatus, Source
from utils.logger import log
from scrapers.base import RawItem

def get_or_create_source(name: str) -> Source:
    with get_session() as session:
        source = session.query(Source).filter_by(name=name).first()
        if not source:
            source = Source(id=uuid.uuid4(), name=name)
            session.add(source)
            session.commit()
            log.info("db_helpers.source_created", name=name)
        return source


def start_ingestion_run(source_id: uuid.UUID) -> IngestionRun:
    with get_session() as session:
        run = IngestionRun(
            source_id  = source_id,
            started_at = datetime.now(),
            status     = "running",
        )
        session.add(run)
        session.commit()
        log.info("db_helpers.run_started", run_id=str(run.id))
        return run


def finish_ingestion_run(
    run_id: uuid.UUID,
    status: str,
    items_scraped:  int = 0,
    items_new:      int = 0,
    items_enriched: int = 0,
    items_embedded: int = 0,
    error_log: str | None = None,
) -> None:
    with get_session() as session:
        run = session.query(IngestionRun).filter_by(id=run_id).first()
        if not run:
            log.warning("db_helpers.run_not_found", run_id=str(run_id))
            return
        run.status          = status
        run.finished_at     = datetime.now()
        run.items_scraped   = items_scraped
        run.items_new       = items_new
        run.items_enriched  = items_enriched
        run.items_embedded  = items_embedded
        run.error_log       = error_log
        session.commit()
        log.info("db_helpers.run_finished", run_id=str(run_id), status=status)


def save_items_deduped(raw_items: list[dict], source_id: uuid.UUID) -> int:
    """
    Bulk insert — skips rows that violate uq_source_external.
    Returns count of actually new rows inserted.
    """
    if not raw_items:
        return 0

    rows = [
        {
            "id"              : uuid.uuid4(),
            "source_id"       : source_id,
            "external_id"     : item.title,  # "owner/repo"
            "url"             : item.url,
            "raw_data"        : asdict(item),
            "scraped_at"      : datetime.now(),
            "pipeline_status" : PipelineStatus.SCRAPED,
            "created_at"      : datetime.now(),
        }
        for item in raw_items
    ]

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


def upsert_content_items(source: Source, raw_items: List[RawItem]) -> List[ContentItem]:
    """Dedup insert. Returns only newly inserted rows (pipeline_status='scraped')."""
    new_items = []

    for raw in raw_items:
        stmt = (
            insert(ContentItem)
            .values(
                source_id=source.id,
                external_id=raw.title,   # "owner/repo"
                url=raw.url,
                raw_data=asdict(raw),    # dataclass → dict for JSON column
            )
            .on_conflict_do_nothing(constraint="uq_source_external")
            .returning(ContentItem.id)
        )
        result = get_session.execute(stmt)
        get_session.commit()

        if result.rowcount > 0:
            new_items.append(get_session.get(ContentItem, result.scalar()))

    return new_items