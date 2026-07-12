# backend/main.py
from fastapi import FastAPI
import uvicorn

from pipelines.runner import run_flow1
from pipelines.personalization import run_digest_pipeline
from utils.logger import log

app = FastAPI()


@app.post("/run/content_pipelines")
def trigger_flow1():
    try:
        result = run_flow1()
        log.info("flow1.completed", result=result)
        return {"status": "completed", "result": result}
    except Exception as e:
        log.error("flow1.failed", error=str(e))
        return {"status": "failed", "error": str(e)}


@app.post("/run/personalized_mail")
def trigger_flow3():
    try:
        result = run_digest_pipeline()
        log.info("flow3.completed", result=result)
        return {"status": "completed", "result": result}
    except Exception as e:
        log.error("flow3.failed", error=str(e))
        return {"status": "failed", "error": str(e)}


@app.get("/health")
def health():
    return {"status": "ok"}