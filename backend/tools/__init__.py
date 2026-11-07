# backend/tools/__init__.py
from tools.github_tools import fetch_github_repo_raw, inspect_github_repo
from tools.hn_tools import fetch_hn_discussion, fetch_hn_discussion_raw, search_hn_discussions

__all__ = [
    "inspect_github_repo",
    "fetch_github_repo_raw",
    "fetch_hn_discussion",
    "fetch_hn_discussion_raw",
    "search_hn_discussions",
]

