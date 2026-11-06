# graphs/state.py
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict

from scrapers.base import RawItem


class ContentIngestionState(TypedDict, total=False):
    """State for the Content Pipeline (Flow 1) LangGraph workflow."""
    source_name: str
    source_id: Optional[str]
    run_id: Optional[str]
    raw_items: List[RawItem]
    new_items_count: int
    enrich_stats: Dict[str, int]
    embed_stats: Dict[str, int]
    status: str
    error: Optional[str]


class UserDigestState(TypedDict, total=False):
    """State for an individual user's Digest Pipeline (Flow 3) LangGraph workflow."""
    user_id: str
    user_name: Optional[str]
    user_email: str
    user_embedding: List[float]
    liked_tags: List[str]
    disliked_tags: List[str]
    include_why_matters: bool
    candidates: List[dict]
    ranked_items: List[dict]
    digest: Optional[dict]
    email_html: Optional[str]
    email_sent: bool
    error: Optional[str]

