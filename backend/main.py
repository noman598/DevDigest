# backend/main.py
from fastapi import FastAPI
import uvicorn
import asyncio

from pipelines.runner import run_flow1
from pipelines.personalization import run_digest_pipeline
from utils.logger import log

app = FastAPI(title="DevSnack Backend API")

sem = asyncio.Semaphore(3)      # Rate limit concurrency


@app.post("/run/content_pipelines")
async def trigger_flow1(source: str = "all"):
    """
    Triggers Flow 1: Scrapes sources (GitHub Trending, OpenAI, Anthropic),
    deduplicates into PostgreSQL, enriches with LangChain ChatGroq, and embeds via Gemini.
    """
    try:
        result = await run_flow1(source_name=source)
        log.info("flow1.completed", result=result)
        return {"status": "completed", "result": result}
    except Exception as e:
        log.error("flow1.failed", error=str(e))
        return {"status": "failed", "error": str(e)}


@app.post("/run/personalized_mail")
async def trigger_flow3():
    """
    Triggers Flow 3: Retrieves matching items via pgvector, ranks by personal taste,
    generates personalized commentary, and delivers email digests via Brevo.
    """
    try:
        result = await run_digest_pipeline()
        log.info("flow3.completed", result=result)
        return {"status": "completed", "result": result}
    except Exception as e:
        log.error("flow3.failed", error=str(e))
        return {"status": "failed", "error": str(e)}


@app.get("/health")
def health():
    return {"status": "ok"}
