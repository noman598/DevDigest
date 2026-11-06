from scrapers.base import BaseScraper, RawItem
from scrapers.github_trending import GitHubTrendingScraper
from scrapers.rss_scraper import (
    RSSFeedScraper,
    OpenAINewsScraper,
    AnthropicNewsScraper,
    AINewsAggregatorScraper,
)

__all__ = [
    "BaseScraper",
    "RawItem",
    "GitHubTrendingScraper",
    "RSSFeedScraper",
    "OpenAINewsScraper",
    "AnthropicNewsScraper",
    "AINewsAggregatorScraper",
]

