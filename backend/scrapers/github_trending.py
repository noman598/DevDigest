"""
Scrapes github.com/trending. Static server-rendered HTML, no JS execution needed.
Respects a custom User-Agent and has retry logic since trending page layout
or availability can occasionally hiccup.
"""
# import requests
import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List

from scrapers.base import BaseScraper, RawItem
from config import config
from utils.logger import log

BASE_URL = "https://github.com/trending"


class GitHubTrendingScraper(BaseScraper):
    source_name = "github_trending"

    def __init__(self, language: str = "", since: str = "daily"):
        self.language = language
        self.since = since

    def _build_url(self) -> str:
        url = BASE_URL
        if self.language:
            url += f"/{self.language}"
        return f"{url}?since={self.since}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _fetch_html(self, url: str) -> str:
        headers = {"User-Agent": config.USER_AGENT}
        # resp = requests.get(url, headers=headers, timeout=15)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text

    async def fetch(self) -> List[RawItem]:
        url = self._build_url()
        log.info("scraping", source=self.source_name, url=url)
        html = await self._fetch_html(url)
        soup = BeautifulSoup(html, "html.parser")

        items: List[RawItem] = []
        repo_articles = soup.select("article.Box-row")

        for article in repo_articles:
            try:
                items.append(self._parse_repo(article))
            except Exception as e:
                # Don't let one malformed entry kill the whole scrape
                log.warning("parse_failed", source=self.source_name, error=str(e))
                continue

        log.info("scrape_complete", source=self.source_name, count=len(items))
        return items

    def _parse_repo(self, article) -> RawItem:
        # Repo name + link
        h2 = article.select_one("h2 a")
        repo_path = h2["href"].strip("/")  # e.g. "owner/repo"
        repo_url = f"https://github.com/{repo_path}"

        # Description (optional, some repos have none)
        desc_tag = article.select_one("p")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # Language (optional)
        lang_tag = article.select_one('[itemprop="programmingLanguage"]')
        language = lang_tag.get_text(strip=True) if lang_tag else "Unknown"

        # Stars today (the trending-specific number) and total stars
        stars_today_tag = article.select_one("span.d-inline-block.float-sm-right")
        stars_today = (
            stars_today_tag.get_text(strip=True).replace(" stars today", "")
            if stars_today_tag
            else "0"
        )

        star_links = article.select('a[href$="/stargazers"]')
        total_stars = star_links[0].get_text(strip=True) if star_links else "0"

        return RawItem(
            source=self.source_name,
            title=repo_path,
            url=repo_url,
            description=description,
            metadata={
                "language": language,
                "stars_today": stars_today,
                "total_stars": total_stars,
            },
        )


