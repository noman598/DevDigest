from config import config
from pipelines.db_helpers import (
    finish_ingestion_run,
    get_or_create_source,
    save_items_deduped,
    start_ingestion_run,
    upsert_content_items,
)
from scrapers.github_trending import GitHubTrendingScraper
from services.embedder import run_embedding
from services.enricher import run_enrichment
from storage.db import init_db
from utils.logger import log


def run_flow1(source_name: str = "github_trending") -> None:
    init_db()

    source = get_or_create_source(source_name)
    run    = start_ingestion_run(source.id)

    try:
        # ── Stage 1: Scrape ───────────────────────────────────────────────────
        log.info("pipeline.stage1.start")
        scraper = GitHubTrendingScraper(
            language=config.GITHUB_TRENDING_LANGUAGE,
            since=config.GITHUB_TRENDING_SINCE,
        )
        raw_items = scraper.fetch()
        # new_content_items = upsert_content_items(source, raw_items)
        log.info("pipeline.stage1.done", count=len(raw_items))

        if not raw_items:
            log.warning("pipeline.stage1.zero_items_returned")
            finish_ingestion_run(run.id, status="completed")
            return

        # ── Stage 2: Save + dedup ─────────────────────────────────────────────
        # Only truly new items get inserted (uq_source_external constraint).
        # Previously-failed items with status='scraped' will be picked up
        # by enricher in Stage 3 — no re-insertion needed.
        new_count = save_items_deduped(raw_items, source_id=source.id)
        # new_content_items = upsert_content_items(source, raw_items)

        log.info("pipeline.stage2.done", new=new_count, total=len(raw_items))

        # ── Stage 3: Enrich ───────────────────────────────────────────────────
        # Picks up ALL items with status='scraped' — including any that failed
        # in a previous run. Batch size keeps LLM costs predictable.
        log.info("pipeline.stage3.start")
        enrich_counts = run_enrichment(batch_size=50)
        log.info("pipeline.stage3.done", **enrich_counts)

        # ── Stage 4: Embed ────────────────────────────────────────────────────
        # Picks up ALL items with status='enriched'.
        log.info("pipeline.stage4.start")
        embed_counts = run_embedding(batch_size=50)
        log.info("pipeline.stage4.done", **embed_counts)

        # finish_ingestion_run(
        #     run.id,
        #     status         = "completed",
        #     items_scraped  = len(raw_items),
        #     items_new      = new_count,
        #     items_enriched = enrich_counts["succeeded"],
        #     items_embedded = embed_counts["succeeded"],
        # )
        # log.info("pipeline.flow1.complete")

    except Exception as e:
        log.error("pipeline.flow1.fatal_error", error=str(e))
        finish_ingestion_run(run.id, status="failed", error_log=str(e))
        raise  # re-raise so scheduler can log it


if __name__ == "__main__":
    run_flow1()