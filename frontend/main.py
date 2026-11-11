"""
StackPulse — Autonomous Developer Intelligence
FastAPI + Jinja2 + HTMX + Tailwind CSS Web Platform
Replaces Streamlit with a production-grade, Embage-inspired SaaS interface.
"""
from datetime import date, datetime
import os
from pathlib import Path
import re
from typing import List, Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from storage import db
from utils.embedding import run_user_embedding
from utils.logger import log

from contextlib import asynccontextmanager

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(
    title="StackPulse · Developer Intelligence",
    description="Autonomous multi-agent intelligence platform for modern developers.",
    version="2.0.0",
    lifespan=lifespan,
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# ── Core Routes ───────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Renders the main landing page, onboarding bento, sample digest & docs."""
    stats = db.get_platform_stats()
    today_str = date.today().strftime("%B %d, %Y")

    default_profile = {
        "email": "",
        "name": "",
        "selected_sources": ["github_trending", "openai_news", "anthropic_news", "hacker_news"],
        "liked_tags": ["AI/ML", "Python", "LLMs", "System Design"],
        "disliked_tags": [],
        "custom_interests": "",
        "keyword_alerts": "",
        "frequency": "daily",
        "delivery_time": "08:00",
        "include_summary": True,
        "include_why_matters": True,
    }

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "profile": default_profile,
            "stats": stats,
            "today": today_str,
        },
    )


@app.post("/api/lookup-profile", response_class=HTMLResponse)
def lookup_profile(
    request: Request,
    email: str = Form(default=""),
):
    """
    HTMX Endpoint: Instant email lookup.
    Re-renders the form pre-populated with existing user preferences if found.
    """
    clean_email = email.strip().lower()
    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        profile = {"email": clean_email}
        msg = "Please enter a valid email address to search."
        return templates.TemplateResponse(
            request=request,
            name="partials/profile_form.html",
            context={"profile": profile, "message": msg},
        )

    existing_profile = db.get_user_profile(clean_email)
    if existing_profile:
        msg = f"Profile found for {clean_email}! Loaded your saved preferences."
        return templates.TemplateResponse(
            request=request,
            name="partials/profile_form.html",
            context={"profile": existing_profile, "message": msg},
        )
    else:
        new_profile = {
            "email": clean_email,
            "selected_sources": ["github_trending", "openai_news", "anthropic_news", "hacker_news"],
            "liked_tags": ["AI/ML", "Python", "LLMs", "System Design"],
            "disliked_tags": [],
            "custom_interests": "",
            "keyword_alerts": "",
            "frequency": "daily",
            "delivery_time": "08:00",
            "include_summary": True,
            "include_why_matters": True,
        }
        msg = f"No prior profile found for {clean_email}. Ready to set up your briefing!"
        return templates.TemplateResponse(
            request=request,
            name="partials/profile_form.html",
            context={"profile": new_profile, "message": msg},
        )


@app.post("/api/save-profile", response_class=HTMLResponse)
def save_profile_endpoint(
    request: Request,
    email: str = Form(...),
    name: Optional[str] = Form(default=""),
    selected_sources: List[str] = Form(default=[]),
    liked_tags: List[str] = Form(default=[]),
    disliked_tags_csv: Optional[str] = Form(default=""),
    custom_interests: Optional[str] = Form(default=""),
    keyword_alerts: Optional[str] = Form(default=""),
    frequency: Optional[str] = Form(default="daily"),
    delivery_time: Optional[str] = Form(default="08:00"),
    include_summary: bool = Form(default=True),
    include_why_matters: bool = Form(default=True),
):
    """
    HTMX Endpoint: Persists user profile to database and executes background embedding.
    Returns the animated save response card.
    """
    clean_email = email.strip().lower()
    if not clean_email or not EMAIL_PATTERN.match(clean_email):
        return HTMLResponse(
            """<div class="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-mono">
                ❌ Error: Please enter a valid email address.
            </div>""",
            status_code=400,
        )

    # Process disliked tags CSV
    disliked_list = [t.strip() for t in (disliked_tags_csv or "").split(",") if t.strip()]

    # If no sources selected, fallback to all default sources
    final_sources = selected_sources or ["github_trending", "openai_news", "anthropic_news", "hacker_news"]

    form_payload = {
        "email": clean_email,
        "name": (name or "").strip(),
        "selected_sources": final_sources,
        "liked_tags": liked_tags,
        "disliked_tags": disliked_list,
        "custom_interests": (custom_interests or "").strip(),
        "keyword_alerts": (keyword_alerts or "").strip(),
        "frequency": frequency or "daily",
        "delivery_time": delivery_time or "08:00",
        "include_summary": bool(include_summary),
        "include_why_matters": bool(include_why_matters),
    }

    try:
        saved = db.save_user_profile(form_payload)
        if not saved:
            return HTMLResponse(
                """<div class="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-mono">
                    ❌ Database error: Unable to commit user preferences. Please check connectivity.
                </div>""",
                status_code=500,
            )

        # Trigger Taste Vectorization
        try:
            run_user_embedding(batch_size=1)
        except Exception as emb_err:
            log.warning("frontend.embedding_warning", email=clean_email, error=str(emb_err))

        return templates.TemplateResponse(
            request=request,
            name="partials/save_response.html",
            context={
                "profile": form_payload,
            },
        )

    except Exception as e:
        log.error("frontend.save_profile_exception", email=clean_email, error=str(e))
        return HTMLResponse(
            f"""<div class="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-mono">
                ❌ Unexpected error: {str(e)}
            </div>""",
            status_code=500,
        )


@app.post("/api/chat", response_class=HTMLResponse)
def chat_assistant(
    request: Request,
    message: str = Form(default=""),
):
    """
    HTMX Endpoint: Handles quick questions about StackPulse via Groq.
    Returns rendered chat bubble partial to append to #chat-messages.
    """
    from utils.assistant import ask_assistant

    clean_message = message.strip()
    if not clean_message:
        return HTMLResponse("")

    answer = ask_assistant(clean_message)

    return templates.TemplateResponse(
        request=request,
        name="partials/chat_message.html",
        context={
            "user_message": clean_message,
            "bot_response": answer,
        },
    )


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestrators and status monitoring."""
    return {
        "status": "healthy",
        "platform": "StackPulse Developer Intelligence",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
