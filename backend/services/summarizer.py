"""
Summarization service. Takes raw scraped items and produces a digest-ready
summary using LangChain ChatGroq.
"""
from typing import List
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from config import config
from utils.logger import log


class SummarizedRepo(BaseModel):
    title: str = Field(description="owner/repo")
    summary: str = Field(description="one-line summary of what it does in plain language")
    why_it_matters: str = Field(description="short clause on why a developer might care")


class SummariesList(BaseModel):
    items: List[SummarizedRepo]


_SUMMARIZE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are summarizing today's trending GitHub repositories for a developer's daily email digest. "
        "Be concise, practical, and skip hype language.",
    ),
    ("human", "{repo_list}"),
])


def summarize_items(items: List) -> List[dict]:
    """
    items: list of items with title, url, description metadata.
    Returns a list of dicts ready for the email template.
    """
    if not items:
        return []

    repo_list = "\n".join(
        f"- {row.get('title') if isinstance(row, dict) else row.title}: "
        f"{(row.get('description') if isinstance(row, dict) else row.description) or 'No description provided'}"
        for row in items
    )

    log.info("summarizing.start", count=len(items))

    llm = ChatGoogleGenerativeAI(
        model=getattr(config, "GEMINI_MODEL", "gemini-3.5-flash-lite"),
        google_api_key=config.GEMINI_API_KEY,
        temperature=0.2,
        max_output_tokens=2000,
    )
    chain = _SUMMARIZE_PROMPT | llm.with_structured_output(SummariesList)

    try:
        result = chain.invoke({"repo_list": repo_list})
        summaries = [item.model_dump() for item in result.items]
    except Exception as e:
        log.error("summary_chain_failed", error=str(e))
        summaries = [
            {
                "title": row.get("title") if isinstance(row, dict) else row.title,
                "summary": (row.get("description") if isinstance(row, dict) else row.description) or "",
                "why_it_matters": "",
            }
            for row in items
        ]

    # Merge URL back in
    url_map = {
        (row.get("title") if isinstance(row, dict) else row.title): (row.get("url") if isinstance(row, dict) else row.url)
        for row in items
    }
    for s in summaries:
        s["url"] = url_map.get(s["title"], "")

    return summaries
