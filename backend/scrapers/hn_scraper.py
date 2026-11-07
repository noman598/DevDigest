# backend/scrapers/hn_scraper.py
"""
Hacker News scraper using the official Firebase REST API.
Implements BaseScraper to seamlessly integrate into the DevSnack content pipeline.
Fetches top/best stories within a configurable time window and minimum score threshold.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
from typing import Any, List, Optional

import httpx

# Add backend directory to sys.path to allow running this script directly
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scrapers.base import BaseScraper, RawItem
from config import config
from utils.logger import log

HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"


class HackerNewsScraper(BaseScraper):
    """
    Scrapes trending and top stories from Hacker News via Firebase API.
    Filters stories by age (defaults to last 24h) and minimum upvote score.
    """

    source_name: str = "hacker_news"

    def __init__(
        self,
        max_age_hours: float = 24.0,
        min_score: int = 30,
        limit: int = 30,
        story_type: str = "topstories",  # "topstories" or "beststories"
    ):
        self.max_age_hours = max_age_hours
        self.min_score = min_score
        self.limit = limit
        self.story_type = story_type

    async def _fetch_story_item(self, client: httpx.AsyncClient, story_id: int) -> Optional[dict]:
        """Fetches a single story JSON from Firebase."""
        url = f"{HN_BASE_URL}/item/{story_id}.json"
        try:
            resp = await client.get(url, timeout=8.0)
            if resp.status_code == 200:
                data = resp.json()
                if data and data.get("type") == "story" and not data.get("deleted") and not data.get("dead"):
                    return data
        except Exception as e:
            log.debug("hn_scraper.fetch_item_failed", story_id=story_id, error=str(e))
        return None

    async def fetch(self) -> List[RawItem]:
        """Fetches, filters, and normalizes top Hacker News stories."""
        log.info(
            "hn_scraper.fetch_start",
            source=self.source_name,
            story_type=self.story_type,
            max_age_hours=self.max_age_hours,
            min_score=self.min_score,
        )

        headers = {
            "User-Agent": getattr(config, "USER_AGENT", "DevSnack-Agent/1.0"),
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(headers=headers, timeout=12.0) as client:
            top_ids_url = f"{HN_BASE_URL}/{self.story_type}.json"
            try:
                resp = await client.get(top_ids_url)
                if resp.status_code != 200:
                    log.error("hn_scraper.fetch_ids_failed", status=resp.status_code)
                    return []
                story_ids = resp.json() or []
            except Exception as e:
                log.error("hn_scraper.request_failed", error=str(e))
                return []

            # Inspect up to the top 60 stories to find matching items
            candidate_ids = story_ids[: min(len(story_ids), self.limit * 2)]

            # Fetch story items with controlled concurrency
            semaphore = asyncio.Semaphore(12)

            async def _fetch_with_sem(sid: int):
                async with semaphore:
                    return await self._fetch_story_item(client, sid)

            tasks = [_fetch_with_sem(sid) for sid in candidate_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=self.max_age_hours)
        cutoff_epoch = int(cutoff_time.timestamp())

        items: List[RawItem] = []
        for res in results:
            if not res or isinstance(res, Exception):
                continue

            story_time = res.get("time", 0)
            score = res.get("score", 0)

            # Apply 24h cutoff filter
            if self.max_age_hours > 0 and story_time < cutoff_epoch:
                continue

            # Apply minimum score filter
            if score < self.min_score:
                continue

            title = res.get("title", "").strip()
            story_id = res.get("id")
            hn_url = f"https://news.ycombinator.com/item?id={story_id}"
            article_url = res.get("url") or hn_url
            comments_count = res.get("descendants", 0)
            author = res.get("by", "unknown")
            kids = res.get("kids", [])[:5]

            published_iso = datetime.fromtimestamp(story_time, tz=timezone.utc).isoformat()
            description = (
                f"Hacker News discussion with {score} points and {comments_count} comments by @{author}."
            )

            raw_item = RawItem(
                source=self.source_name,
                title=title,
                url=article_url,
                description=description,
                metadata={
                    "id": story_id,
                    "guid": f"hn:{story_id}",
                    "score": score,
                    "comments_count": comments_count,
                    "by": author,
                    "hn_url": hn_url,
                    "top_comment_ids": kids,
                    "published_at": published_iso,
                    "categories": ["Hacker News", "Tech Discussion"],
                },
            )
            items.append(raw_item)
            if len(items) >= self.limit:
                break

        log.info("hn_scraper.fetch_complete", count=len(items))
        return items


# CLI runner
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hacker News scraper for DevSnack")
    parser.add_argument("--hours", type=float, default=24.0, help="Cutoff age in hours (default: 24)")
    parser.add_argument("--min-score", type=int, default=20, help="Minimum HN score (default: 20)")
    parser.add_argument("--limit", type=int, default=10, help="Maximum stories to return (default: 10)")
    args = parser.parse_args()

    async def main():
        scraper = HackerNewsScraper(max_age_hours=args.hours, min_score=args.min_score, limit=args.limit)
        items = await scraper.fetch()
        print(f"\n--- Found {len(items)} Hacker News stories ---")
        for idx, item in enumerate(items, start=1):
            meta = item.metadata
            print(f"{idx}. [{meta['score']} pts | {meta['comments_count']} comments] {item.title}")
            print(f"   URL: {item.url}")
            print(f"   HN:  {meta['hn_url']}\n")

    asyncio.run(main())

