"""
Orchestrator. Run this daily (via cron or APScheduler — see scheduler.py).

Pipeline:
1. Scrape GitHub Trending
2. Save to DB, get only NEW items (dedup)
3. If no new items, skip (don't send empty digest)
4. Summarize new items via Claude
5. Email the digest
6. Log that digest was sent (idempotency — safe to re-run same day)
"""
from backend.config import config
from backend.storage.db import init_db, save_items_dev, was_digest_sent_today, log_digest_sent, get_items_last_24h
from backend.scrapers.github_trending import GitHubTrendingScraper
from backend.services.summarizer import summarize_items
from backend.services.mailer import send_digest
from backend.utils.logger import log


def run_pipeline():
    config.validate_required()
    init_db()

    if was_digest_sent_today(config.EMAIL_TO):
        log.info("digest_already_sent_today", to=config.EMAIL_TO)
        return

    # 1. Scrape
    scraper = GitHubTrendingScraper(
        language=config.GITHUB_TRENDING_LANGUAGE,
        since=config.GITHUB_TRENDING_SINCE,
    )
    try:
        raw_items = scraper.fetch()
    except Exception as e:
        log.error("scrape_failed", source=scraper.source_name, error=str(e))
        return  # fail gracefully — don't crash, just skip today's run

    if not raw_items:
        log.warning("scrape_returned_zero_items", source=scraper.source_name)
        return

    # 2. Save + dedup
    new_items = save_items_dev(raw_items)

    # if not new_items:
    #     log.info("no_new_items_today")
    #     return

    # 3. Pull fresh rows back from DB for the summarizer (consistent schema)
    items_for_digest = get_items_last_24h(source="github_trending")

    # 4. Summarize
    try:
        summaries = summarize_items(items_for_digest)
        print(summaries)
    except Exception as e:
        log.error("summarization_failed", error=str(e))
        return

    # 5. Send email
    sent = send_digest(summaries, config.EMAIL_TO)

    # 6. Log for idempotency
    if sent:
        log_digest_sent(config.EMAIL_TO, len(summaries))

    # log.info("pipeline_complete", new_items=len(new_items), emailed=sent)


if __name__ == "__main__":
    run_pipeline()
