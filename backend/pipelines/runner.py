# pipelines/runner.py
import asyncio
from graphs.content_graph import run_content_pipeline_graph
from utils.logger import log


async def run_flow1(source_name: str = "all") -> dict:
    """
    Executes the Flow 1 Content Ingestion & Enrichment Pipeline
    powered by LangGraph.
    Scrapes GitHub Trending and AI News (OpenAI, Anthropic) by default.
    """
    log.info("pipeline.flow1.langgraph.start", source=source_name)
    result = await run_content_pipeline_graph(source_name=source_name)
    log.info("pipeline.flow1.langgraph.complete", result=result)
    return result


if __name__ == "__main__":
    asyncio.run(run_flow1())
