"""
Summarization service. Takes raw scraped items and produces a digest-ready
summary using Groq. Batches everything into ONE API call instead of
one-per-item — cheaper and faster.
"""
import json
from typing import List
from groq import Groq

from backend.config import config
from backend.utils.logger import log

SYSTEM_PROMPT = """You are summarizing today's trending GitHub repositories for a \
developer's daily email digest. Be concise, practical, and skip hype language.

For each repo, write:
- A one-line summary of what it does (in plain language, not marketing-speak)
- Why a developer might care (one short clause)

Respond ONLY with valid JSON, no markdown fences, no preamble. Format:
[
  {"title": "owner/repo", "summary": "...", "why_it_matters": "..."}
]
"""


def summarize_items(items: List) -> List[dict]:
    """
    items: list of sqlite3.Row objects (from storage.db) with title, url,
    description, metadata columns.
    Returns a list of dicts ready for the email template.
    """
    if not items:
        return []

    client = Groq(api_key=config.GROQ_API_KEY)

    repo_list = "\n".join(
        f"- {row['title']}: {row['description'] or 'No description provided'}"
        for row in items
    )

    log.info("summarizing", count=len(items))

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": repo_list},
        ],
    )

    raw_text = response.choices[0].message.content.strip()

    try:
        summaries = json.loads(raw_text)
    except json.JSONDecodeError:
        log.error("summary_parse_failed", raw=raw_text[:500])
        # Fallback: return items without AI summary rather than failing the whole digest
        summaries = [
            {"title": row["title"], "summary": row["description"] or "", "why_it_matters": ""}
            for row in items
        ]

    # Merge URL back in (LLM doesn't need to handle URLs, reduces hallucination risk)
    url_map = {row["title"]: row["url"] for row in items}
    for s in summaries:
        s["url"] = url_map.get(s["title"], "")

    return summaries