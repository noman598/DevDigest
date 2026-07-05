"""
Optional: run the pipeline on a daily schedule without relying on system cron.
Useful for platforms like Railway/Render where you just run one long-lived process.

Usage: python scheduler.py
(leave running — it will trigger run_pipeline() every day at the set hour)
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from backend.main import run_pipeline
from backend.utils.logger import log

DAILY_RUN_HOUR_UTC = 8  # change to your preferred send time, in UTC


def start():
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(run_pipeline, "cron", hour=DAILY_RUN_HOUR_UTC, minute=0)

    log.info("scheduler_started", run_hour_utc=DAILY_RUN_HOUR_UTC)

    # Run once immediately on startup too, so you don't wait a full day to test
    run_pipeline()

    scheduler.start()


if __name__ == "__main__":
    start()
