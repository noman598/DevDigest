"""
RSS / Atom feed scraper for AI news (OpenAI, Anthropic, etc.).
Implements BaseScraper to seamlessly integrate into the DevSnack content pipeline,
while also functioning as a standalone scraper.
Filters items by a configurable time window (defaults to the last 24 hours).
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import sys
from typing import Any, List, Optional
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
import dateutil.parser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

# Add backend directory to sys.path to allow running this script directly
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scrapers.base import BaseScraper, RawItem
from config import config
from utils.logger import log


# Default feed endpoints for leading AI labs
FEED_URLS = {
    "openai": {
        "name": "openai_news",
        "url": "https://openai.com/news/rss.xml",
        "description": "OpenAI official news and announcements",
    },
    "anthropic_news": {
        "name": "anthropic_news",
        "url": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml",
        "description": "Anthropic official news and announcements (curated feed)",
    },
    "anthropic_research": {
        "name": "anthropic_research",
        "url": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_research.xml",
        "description": "Anthropic research papers and technical reports",
    },
}


def _clean_html(text: str) -> str:
    """Strip HTML markup and collapse extraneous whitespace."""
    if not text:
        return ""
    if "<" not in text:
        return " ".join(text.split())
    soup = BeautifulSoup(text, "html.parser")
    cleaned = soup.get_text(separator=" ", strip=True)
    return " ".join(cleaned.split())


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse RFC 2822 or ISO 8601 date strings into aware UTC datetime."""
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    try:
        dt = dateutil.parser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


class RSSFeedScraper(BaseScraper):
    """
    Generic RSS / Atom feed scraper.
    Produces standardized RawItem objects matching the DevSnack content pipeline.
    By default, restricts items to the last 24 hours (`max_age_hours=24.0`).
    """

    def __init__(
        self,
        feed_url: str,
        source_name: str = "rss_feed",
        limit: Optional[int] = None,
        max_age_hours: Optional[float] = 24.0,
    ):
        self.feed_url = feed_url
        self.source_name = source_name
        self.limit = limit
        self.max_age_hours = max_age_hours

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _fetch_xml(self) -> str:
        headers = {
            "User-Agent": getattr(config, "USER_AGENT", "DevSnackNewsBot/1.0"),
            "Accept": "application/rss+xml, application/xml, text/xml, application/atom+xml, */*",
        }
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(self.feed_url, headers=headers)
            resp.raise_for_status()
            return resp.text

    def _parse_rss_item(self, item_elem: ET.Element) -> Optional[RawItem]:
        title = (item_elem.findtext("title") or "").strip()
        link = (item_elem.findtext("link") or "").strip()
        description = item_elem.findtext("description") or ""

        # Handle namespaces if present for content:encoded
        content_encoded = None
        for child in item_elem:
            if child.tag.endswith("encoded"):
                content_encoded = child.text
                break

        full_desc = description or content_encoded or ""
        clean_desc = _clean_html(full_desc)

        # Dates & Categories
        pub_date_raw = item_elem.findtext("pubDate")
        pub_dt = _parse_date(pub_date_raw)

        categories = [
            c.text.strip()
            for c in item_elem.findall("category")
            if c.text and c.text.strip()
        ]

        guid = item_elem.findtext("guid") or link

        # ── 24-Hour Time Filter ──────────────────────────────────────────────
        if self.max_age_hours is not None and pub_dt:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)
            if pub_dt < cutoff:
                return None  # Older than cutoff window

        if not title and not link:
            return None

        return RawItem(
            source=self.source_name,
            title=title or "Untitled",
            url=link or guid,
            description=clean_desc[:1000],  # trim excessive bodies
            metadata={
                "published_at": pub_dt.isoformat() if pub_dt else pub_date_raw,
                "categories": categories,
                "guid": guid,
                "feed_url": self.feed_url,
            },
        )

    def _parse_atom_entry(self, entry_elem: ET.Element) -> Optional[RawItem]:
        # Atom elements often use {http://www.w3.org/2005/Atom} namespace
        def _find(elem, tag_name: str) -> Optional[ET.Element]:
            for ch in elem:
                if ch.tag.split("}")[-1] == tag_name:
                    return ch
            return None

        title_elem = _find(entry_elem, "title")
        title = (title_elem.text or "").strip() if title_elem is not None else "Untitled"

        # Link can be <link href="..."/>
        link = ""
        for ch in entry_elem:
            if ch.tag.split("}")[-1] == "link":
                link = ch.attrib.get("href", ch.text or "")
                if link:
                    break

        summary_elem = _find(entry_elem, "summary") or _find(entry_elem, "content")
        desc_raw = (summary_elem.text or "") if summary_elem is not None else ""
        clean_desc = _clean_html(desc_raw)

        date_elem = _find(entry_elem, "published") or _find(entry_elem, "updated")
        pub_date_raw = date_elem.text if date_elem is not None else None
        pub_dt = _parse_date(pub_date_raw)

        id_elem = _find(entry_elem, "id")
        guid = (id_elem.text or "") if id_elem is not None else link

        # ── 24-Hour Time Filter ──────────────────────────────────────────────
        if self.max_age_hours is not None and pub_dt:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=self.max_age_hours)
            if pub_dt < cutoff:
                return None

        return RawItem(
            source=self.source_name,
            title=title,
            url=link or guid,
            description=clean_desc[:1000],
            metadata={
                "published_at": pub_dt.isoformat() if pub_dt else pub_date_raw,
                "guid": guid,
                "feed_url": self.feed_url,
            },
        )

    async def fetch(self) -> List[RawItem]:
        """Asynchronously fetch and parse the feed items."""
        log.info(
            "scraping.rss.start",
            source=self.source_name,
            url=self.feed_url,
            max_age_hours=self.max_age_hours,
        )
        xml_content = await self._fetch_xml()

        try:
            root = ET.fromstring(xml_content.encode("utf-8"))
        except ET.ParseError as e:
            log.error("scraping.rss.parse_xml_error", url=self.feed_url, error=str(e))
            raise

        items: List[RawItem] = []

        # Check for RSS 2.0 (<channel><item>)
        rss_items = root.findall(".//item")
        if rss_items:
            for it in rss_items:
                parsed = self._parse_rss_item(it)
                if parsed:
                    items.append(parsed)
                if self.limit and len(items) >= self.limit:
                    break

        # Check for Atom (<entry>)
        else:
            atom_entries = [ch for ch in root.iter() if ch.tag.split("}")[-1] == "entry"]
            for entry in atom_entries:
                parsed = self._parse_atom_entry(entry)
                if parsed:
                    items.append(parsed)
                if self.limit and len(items) >= self.limit:
                    break

        log.info(
            "scraping.rss.complete",
            source=self.source_name,
            total_fetched=len(items),
            feed=self.feed_url,
            max_age_hours=self.max_age_hours,
        )
        return items

    def fetch_sync(self) -> List[RawItem]:
        """Convenience synchronous fetch wrapper."""
        return asyncio.run(self.fetch())


class OpenAINewsScraper(RSSFeedScraper):
    """Specialized scraper for OpenAI news feed with 24-hour window by default."""

    def __init__(
        self,
        limit: Optional[int] = None,
        max_age_hours: Optional[float] = 24.0,
    ):
        super().__init__(
            feed_url=FEED_URLS["openai"]["url"],
            source_name="openai_news",
            limit=limit,
            max_age_hours=max_age_hours,
        )


class AnthropicNewsScraper(RSSFeedScraper):
    """Specialized scraper for Anthropic news & research feeds with 24-hour window by default."""

    def __init__(
        self,
        include_research: bool = True,
        limit: Optional[int] = None,
        max_age_hours: Optional[float] = 24.0,
    ):
        super().__init__(
            feed_url=FEED_URLS["anthropic_news"]["url"],
            source_name="anthropic_news",
            limit=limit,
            max_age_hours=max_age_hours,
        )
        self.include_research = include_research

    async def fetch(self) -> List[RawItem]:
        # Fetch news feed
        items = await super().fetch()

        if self.include_research:
            research_scraper = RSSFeedScraper(
                feed_url=FEED_URLS["anthropic_research"]["url"],
                source_name="anthropic_research",
                limit=self.limit,
                max_age_hours=self.max_age_hours,
            )
            research_items = await research_scraper.fetch()
            items.extend(research_items)

        # Re-sort descending by published date if present
        def _get_pub_date(item: RawItem) -> str:
            return item.metadata.get("published_at") or ""

        items.sort(key=_get_pub_date, reverse=True)
        if self.limit:
            items = items[: self.limit]
        return items


class AINewsAggregatorScraper(BaseScraper):
    """
    Scrapes news from multiple AI labs (OpenAI, Anthropic) in parallel
    and aggregates them into a single chronological feed filtered to the last 24 hours.
    """

    source_name = "ai_news_rss"

    def __init__(
        self,
        limit_per_source: Optional[int] = None,
        max_age_hours: Optional[float] = 24.0,
    ):
        self.scrapers: List[BaseScraper] = [
            OpenAINewsScraper(limit=limit_per_source, max_age_hours=max_age_hours),
            AnthropicNewsScraper(
                include_research=True,
                limit=limit_per_source,
                max_age_hours=max_age_hours,
            ),
        ]

    async def fetch(self) -> List[RawItem]:
        log.info("ai_news_aggregator.start", scrapers_count=len(self.scrapers))
        tasks = [scraper.fetch() for scraper in self.scrapers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        combined: List[RawItem] = []
        for scraper, res in zip(self.scrapers, results):
            if isinstance(res, Exception):
                log.error("ai_news_aggregator.scraper_failed", scraper=scraper.source_name, error=str(res))
                continue
            combined.extend(res)

        # Sort descending by published_at
        combined.sort(
            key=lambda item: item.metadata.get("published_at") or "",
            reverse=True,
        )
        log.info("ai_news_aggregator.complete", total_items=len(combined))
        return combined


# ─────────────────────────────────────────────────────────────────────────────
# CLI Standalone runner for testing and manual scraping
# ─────────────────────────────────────────────────────────────────────────────
async def _main():
    parser = argparse.ArgumentParser(description="Fetch latest AI news from OpenAI and Anthropic RSS feeds.")
    parser.add_argument(
        "--source",
        choices=["all", "openai", "anthropic"],
        default="all",
        help="Source to scrape (default: all)",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=24.0,
        help="Only collect items published in the last N hours (default: 24.0). Pass 0 to disable.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max items to fetch per source (default: unlimited within time window)",
    )
    parser.add_argument(
        "--save",
        type=str,
        default=None,
        help="Optional path to save results as JSON (e.g. data/ai_news.json)",
    )
    args = parser.parse_args()

    max_age_hours = args.hours if args.hours > 0 else None
    window_label = f"last {max_age_hours} hours" if max_age_hours else "all time"
    print(f"Fetching AI news (source: {args.source}, window: {window_label}, limit: {args.limit})...\n")

    if args.source == "openai":
        scraper = OpenAINewsScraper(limit=args.limit, max_age_hours=max_age_hours)
    elif args.source == "anthropic":
        scraper = AnthropicNewsScraper(limit=args.limit, max_age_hours=max_age_hours)
    else:
        scraper = AINewsAggregatorScraper(limit_per_source=args.limit, max_age_hours=max_age_hours)

    items = await scraper.fetch()

    print(f"\nSuccessfully scraped {len(items)} items from {window_label}:\n" + "=" * 80)
    for idx, it in enumerate(items, 1):
        pub = it.metadata.get("published_at", "N/A")
        print(f"[{idx}] [{it.source.upper()}] {it.title}")
        print(f"    Published: {pub}")
        print(f"    URL:       {it.url}")
        print(f"    Desc:      {it.description[:140]}..." if len(it.description) > 140 else f"    Desc:      {it.description}")
        print("-" * 80)

    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "source": it.source,
                "title": it.title,
                "url": it.url,
                "description": it.description,
                "metadata": it.metadata,
            }
            for it in items
        ]
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\nSaved {len(items)} items to {save_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(_main())
