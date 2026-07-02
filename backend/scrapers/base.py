"""
Common interface for all scrapers. Every source (GitHub Trending, HN, Reddit, etc.)
implements this same shape, so the orchestrator never needs to know source-specific details.
This is what makes adding a new source later a clean, isolated change.
"""
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import List


@dataclass
class RawItem:
    """Normalized shape every scraped item gets converted into."""
    source: str          # e.g. "github_trending"
    title: str            # e.g. repo name "owner/repo"
    url: str
    description: str
    metadata: dict        # source-specific extras (stars, language, etc.)


class BaseScraper(ABC):
    """All scrapers inherit this. Forces a consistent fetch() contract."""

    source_name: str = "base"

    @abstractmethod
    def fetch(self) -> List[RawItem]:
        """Fetch and return a list of RawItem. Must raise on failure, not return []."""
        raise NotImplementedError
