# pipeline/personalization.py
import asyncio
from graphs.digest_graph import run_digest_pipeline_graph
from utils.logger import log


async def run_digest_pipeline(top_n: int = 5) -> dict[str, int]:
    """
    Executes the Flow 3 Personalized Digest Pipeline
    powered by LangGraph.
    """
    log.info("pipeline.flow3.langgraph.start")
    counts = await run_digest_pipeline_graph(top_n=top_n)
    log.info("pipeline.flow3.langgraph.complete", **counts)
    return counts


if __name__ == "__main__":
    asyncio.run(run_digest_pipeline())
