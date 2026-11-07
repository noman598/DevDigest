# graphs/content_graph.py
import asyncio
from typing import Literal
import uuid

from langgraph.graph import StateGraph, START, END

from config import config
from graphs.state import ContentIngestionState
from pipelines.db_helpers import (
    finish_ingestion_run,
    get_or_create_source,
    save_items_deduped,
    start_ingestion_run,
)
from scrapers.github_trending import GitHubTrendingScraper
from scrapers.hn_scraper import HackerNewsScraper
from scrapers.rss_scraper import AINewsAggregatorScraper, OpenAINewsScraper, AnthropicNewsScraper
from services.embedder import run_embedding
from services.enricher import run_enrichment
from storage.db import init_db
from utils.logger import log


# ── Graph Nodes ───────────────────────────────────────────────────────────────

def init_run_node(state: ContentIngestionState) -> dict:
    """Initializes the database and logs a new ingestion run."""
    init_db()
    source_name = state.get("source_name", "all")
    source_id = get_or_create_source(source_name)
    run = start_ingestion_run(source_id)

    log.info("graph.content.init_run", source=source_name, run_id=str(run.id))
    return {
        "source_name": source_name,
        "source_id": str(source_id),
        "run_id": str(run.id),
        "status": "running",
    }


async def scrape_node(state: ContentIngestionState) -> dict:
    """Asynchronously scrapes content across GitHub Trending and AI News (OpenAI, Anthropic)."""
    source_name = state.get("source_name", "all")
    log.info("graph.content.scrape_start", source=source_name)

    scrapers = []
    if source_name == "github_trending":
        scrapers.append(
            GitHubTrendingScraper(
                language=getattr(config, "GITHUB_TRENDING_LANGUAGE", ""),
                since=getattr(config, "GITHUB_TRENDING_SINCE", "daily"),
            )
        )
    elif source_name in ("openai_news", "openai"):
        scrapers.append(OpenAINewsScraper(max_age_hours=24.0))
    elif source_name in ("anthropic_news", "anthropic"):
        scrapers.append(AnthropicNewsScraper(max_age_hours=24.0))
    elif source_name in ("ai_news_rss", "rss", "ai_news"):
        scrapers.append(AINewsAggregatorScraper(max_age_hours=24.0))
    elif source_name in ("hacker_news", "hn"):
        scrapers.append(HackerNewsScraper(max_age_hours=24.0, min_score=25, limit=25))
    elif source_name == "all":
        # Scrapes GitHub Trending, AI Lab news (OpenAI, Anthropic), and Hacker News in parallel
        scrapers.append(
            GitHubTrendingScraper(
                language=getattr(config, "GITHUB_TRENDING_LANGUAGE", ""),
                since=getattr(config, "GITHUB_TRENDING_SINCE", "daily"),
            )
        )
        scrapers.append(AINewsAggregatorScraper(max_age_hours=24.0))
        scrapers.append(HackerNewsScraper(max_age_hours=24.0, min_score=25, limit=25))
    else:
        scrapers.append(HackerNewsScraper(max_age_hours=24.0, min_score=25, limit=25))

    tasks = [scraper.fetch() for scraper in scrapers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    raw_items = []
    for res in results:
        if isinstance(res, Exception):
            log.error("graph.content.scraper_failed", error=str(res))
            continue
        raw_items.extend(res)

    log.info("graph.content.scrape_done", items_count=len(raw_items))
    return {"raw_items": raw_items}


def check_scraped_items(state: ContentIngestionState) -> Literal["dedup_node", "finalize_node"]:
    """Conditional Edge: routes directly to finalize if no items were scraped."""
    raw_items = state.get("raw_items", [])
    if not raw_items:
        log.warning("graph.content.zero_items_scraped")
        return "finalize_node"
    return "dedup_node"


def dedup_node(state: ContentIngestionState) -> dict:
    """
    Saves new items into PostgreSQL, filtering out duplicates via unique constraints.
    Maps each item to its true source (github_trending, openai_news, anthropic_news).
    """
    raw_items = state.get("raw_items", [])
    source_id = uuid.UUID(state["source_id"]) if state.get("source_id") else None
    new_count = save_items_deduped(raw_items, default_source_id=source_id)

    log.info("graph.content.dedup_done", new_items=new_count, total_scraped=len(raw_items))
    return {"new_items_count": new_count}


async def enrich_node(state: ContentIngestionState) -> dict:
    """Enriches scraped items with LLM summaries, tech stack, and topics via LangChain."""
    log.info("graph.content.enrich_start")
    enrich_counts = await run_enrichment(batch_size=50)
    log.info("graph.content.enrich_done", **enrich_counts)
    return {"enrich_stats": enrich_counts}


def embed_node(state: ContentIngestionState) -> dict:
    """Generates 1536-dim vector embeddings for enriched content via LangChain Google GenAI."""
    log.info("graph.content.embed_start")
    embed_counts = run_embedding(batch_size=50)
    log.info("graph.content.embed_done", **embed_counts)
    return {"embed_stats": embed_counts, "status": "completed"}


def finalize_node(state: ContentIngestionState) -> dict:
    """Finalizes the ingestion run in the database with summary stats."""
    run_id_str = state.get("run_id")
    if run_id_str:
        run_id = uuid.UUID(run_id_str)
        status = state.get("status", "completed")
        enrich_stats = state.get("enrich_stats", {})
        embed_stats = state.get("embed_stats", {})

        finish_ingestion_run(
            run_id=run_id,
            status=status,
            items_scraped=len(state.get("raw_items", [])),
            items_new=state.get("new_items_count", 0),
            items_enriched=enrich_stats.get("succeeded", 0),
            items_embedded=embed_stats.get("succeeded", 0),
            error_log=state.get("error"),
        )
    log.info("graph.content.pipeline_complete", status=state.get("status"))
    return state


# ── Graph Builder ─────────────────────────────────────────────────────────────

def build_content_graph():
    builder = StateGraph(ContentIngestionState)

    builder.add_node("init_run_node", init_run_node)
    builder.add_node("scrape_node", scrape_node)
    builder.add_node("dedup_node", dedup_node)
    builder.add_node("enrich_node", enrich_node)
    builder.add_node("embed_node", embed_node)
    builder.add_node("finalize_node", finalize_node)

    # Define Workflow Edges
    builder.add_edge(START, "init_run_node")
    builder.add_edge("init_run_node", "scrape_node")
    builder.add_conditional_edges(
        "scrape_node",
        check_scraped_items,
        {
            "dedup_node": "dedup_node",
            "finalize_node": "finalize_node",
        },
    )
    builder.add_edge("dedup_node", "enrich_node")
    builder.add_edge("enrich_node", "embed_node")
    builder.add_edge("embed_node", "finalize_node")
    builder.add_edge("finalize_node", END)

    return builder.compile()


content_graph = build_content_graph()


async def run_content_pipeline_graph(source_name: str = "all") -> dict:
    """Executes the LangGraph content pipeline across all sources."""
    initial_state: ContentIngestionState = {
        "source_name": source_name,
        "raw_items": [],
        "new_items_count": 0,
        "enrich_stats": {},
        "embed_stats": {},
        "status": "pending",
    }
    return await content_graph.ainvoke(initial_state)
