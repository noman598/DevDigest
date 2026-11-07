# backend/tools/hn_tools.py
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import httpx
from langchain_core.tools import tool

from config import config
from utils.logger import log

HN_API_BASE = "https://hacker-news.firebaseio.com/v0"
HN_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"


def _extract_hn_story_id(story_input: Any) -> Optional[int]:
    """Extracts integer story ID from an int, string ID, or full HN URL."""
    if isinstance(story_input, int):
        return story_input

    if not story_input:
        return None

    str_val = str(story_input).strip()
    # Check if direct integer
    if str_val.isdigit():
        return int(str_val)

    # Check for hn:12345 format
    if str_val.startswith("hn:"):
        rem = str_val.split(":", 1)[1]
        if rem.isdigit():
            return int(rem)

    # Check for URL with id= query param
    match = re.search(r"id=(\d+)", str_val)
    if match:
        return int(match.group(1))

    return None


def _clean_comment_html(html_text: str) -> str:
    """Strips HTML tags and entity codes from Hacker News comments."""
    if not html_text:
        return ""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        # Collapse repeated spaces/newlines
        return re.sub(r"\s+", " ", text)
    except Exception:
        # Fallback regex strip
        clean = re.sub(r"<[^>]+>", " ", html_text)
        return re.sub(r"\s+", " ", clean).strip()


def fetch_hn_discussion_raw(story_id_input: Any, max_comments: int = 4) -> Dict[str, Any]:
    """
    Fetches raw story metadata and top root comments from Hacker News Firebase API.
    Returns structured data for programmatic usage.
    """
    story_id = _extract_hn_story_id(story_id_input)
    if not story_id:
        return {"success": False, "error": f"Invalid Hacker News story ID: {story_id_input}"}

    headers = {
        "User-Agent": getattr(config, "USER_AGENT", "DevSnack-Agent/1.0"),
        "Accept": "application/json",
    }

    try:
        with httpx.Client(headers=headers, timeout=10.0) as client:
            # 1. Fetch story details
            story_resp = client.get(f"{HN_API_BASE}/item/{story_id}.json")
            if story_resp.status_code != 200:
                return {"success": False, "error": f"Failed to fetch story {story_id}: HTTP {story_resp.status_code}"}

            story = story_resp.json()
            if not story:
                return {"success": False, "error": f"Story {story_id} not found on Hacker News."}

            title = story.get("title", "")
            score = story.get("score", 0)
            comments_count = story.get("descendants", 0)
            by = story.get("by", "unknown")
            kids = story.get("kids", [])[:max_comments]

            # 2. Fetch top comments
            top_comments: List[Dict[str, str]] = []
            for kid_id in kids:
                try:
                    c_resp = client.get(f"{HN_API_BASE}/item/{kid_id}.json", timeout=5.0)
                    if c_resp.status_code == 200:
                        c_data = c_resp.json()
                        if c_data and not c_data.get("deleted") and not c_data.get("dead"):
                            clean_text = _clean_comment_html(c_data.get("text", ""))
                            if clean_text:
                                top_comments.append({
                                    "by": c_data.get("by", "anonymous"),
                                    "text": clean_text[:220],
                                })
                except Exception as e:
                    log.debug("hn_tools.comment_fetch_error", kid=kid_id, error=str(e))

            return {
                "success": True,
                "story_id": story_id,
                "title": title,
                "score": score,
                "comments_count": comments_count,
                "by": by,
                "hn_url": f"https://news.ycombinator.com/item?id={story_id}",
                "comments": top_comments,
            }

    except httpx.RequestError as exc:
        log.warning("hn_tools.request_failed", story_id=story_id, error=str(exc))
        return {"success": False, "error": f"Network error contacting Hacker News API: {str(exc)}"}


@tool
def fetch_hn_discussion(story_id: str) -> str:
    """
    Fetches the top community discussion, opinions, and critiques for a Hacker News story.
    Use this tool to extract real community consensus, sentiment, warnings, and developer reactions
    for an item before summarizing or enriching it.

    Args:
        story_id: The Hacker News story ID (e.g. '41234567') or HN thread URL.

    Returns:
        A concise summary of the story's points, total comments, and top community commentary (~100 tokens).
    """
    data = fetch_hn_discussion_raw(story_id, max_comments=4)
    if not data.get("success"):
        return f"Could not fetch Hacker News discussion: {data.get('error')}"

    comments = data.get("comments", [])
    if not comments:
        return (
            f"Hacker News Thread: '{data['title']}'\n"
            f"Score: {data['score']} points | Comments: {data['comments_count']} | By: @{data['by']}\n"
            f"Community Discussion: No top-level comments posted yet."
        )

    formatted_comments = "\n".join(
        f"- @{c['by']}: \"{c['text']}...\"" for c in comments
    )

    return (
        f"Hacker News Thread: '{data['title']}'\n"
        f"Score: {data['score']} points | Comments: {data['comments_count']} | By: @{data['by']}\n"
        f"Top Community Highlights:\n"
        f"{formatted_comments}"
    )


@tool
def search_hn_discussions(query: str) -> str:
    """
    Searches Hacker News for relevant past community threads and debates about a technology or topic.
    Use this tool when you need developer opinions or past sentiment about a specific framework or tool.

    Args:
        query: Search keywords, e.g. 'FastAPI vs Litestar' or 'DuckDB'.

    Returns:
        Top 3 matching Hacker News threads with their scores, comment counts, and links (~60 tokens).
    """
    headers = {
        "User-Agent": getattr(config, "USER_AGENT", "DevSnack-Agent/1.0"),
        "Accept": "application/json",
    }
    url = f"{HN_ALGOLIA_BASE}/search"
    params = {"query": query, "tags": "story", "hitsPerPage": 3}

    try:
        with httpx.Client(headers=headers, timeout=8.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code != 200:
                return f"Hacker News search returned HTTP {resp.status_code}"

            hits = resp.json().get("hits", [])
            if not hits:
                return f"No Hacker News discussions found for query '{query}'."

            lines = []
            for h in hits:
                pts = h.get("points") or 0
                comms = h.get("num_comments") or 0
                title = h.get("title") or "Untitled"
                story_id = h.get("objectID")
                lines.append(f"- \"{title}\" ({pts} pts, {comms} comments) -> https://news.ycombinator.com/item?id={story_id}")

            return f"Top Hacker News discussions for '{query}':\n" + "\n".join(lines)

    except Exception as e:
        return f"Error searching Hacker News: {str(e)}"

