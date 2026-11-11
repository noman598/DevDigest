"""
StackPulse Assistant - Simple, lightweight chatbot powered by Groq.
Responds concisely to user questions about StackPulse in <= 2 sentences.
"""
import os
import re
from groq import Groq
from config import config
from utils.logger import log

SYSTEM_PROMPT = """You are the StackPulse Assistant.
StackPulse is a daily developer intelligence platform.
It continuously ingests updates from:
1. GitHub Trending repositories
2. Official AI research releases (OpenAI, Anthropic)
3. Active CVE security advisories from the National Vulnerability Database (NVD)
4. High-signal engineering discussions on Hacker News

It filters and matches updates to each developer's chosen stack (languages, frameworks, topics).
It synthesizes one concise 2-minute morning email delivered at 8:00 AM daily.
It enforces a 7-day memory deduplication window so users never see repeat stories.
It is zero-spam and free of advertising tracking.

RULES:
1. Answer the user's question about StackPulse accurately and helpfully.
2. Your response MUST be strictly 1 or 2 sentences maximum. Never exceed 2 sentences.
3. Be friendly, direct, and concise."""

# Candidate models in order of priority (fastest & lightweight first)
GROQ_MODELS = [
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]

def _get_fallback_reply(query: str) -> str:
    """Fast, accurate fallback replies if Groq is unreachable or fails."""
    q = query.lower()
    if any(k in q for k in ["what is", "about", "how it work", "overview"]):
        return "StackPulse is a curated developer briefing that scans GitHub, top AI labs, and Hacker News to deliver a 2-minute email matched to your stack every morning at 8:00 AM."
    if any(k in q for k in ["source", "where", "track", "github", "news"]):
        return "StackPulse monitors GitHub Trending, official releases from OpenAI and Anthropic, active NVD CVE advisories, and top Hacker News discussions."
    if any(k in q for k in ["security", "cve", "vulnerab", "audit"]):
        return "We run daily automated checks against the National Vulnerability Database to warn you about critical CVEs affecting your dependencies before they hit production."
    if any(k in q for k in ["subscribe", "sign up", "join", "cost", "free"]):
        return "You can customize your stack and subscribe directly below in the 'Personalize Your Daily Briefing' section with just your email."
    if any(k in q for k in ["duplicate", "repeat", "memory"]):
        return "StackPulse features 7-day memory deduplication so you never receive the same repository or announcement twice in a rolling week."
    if any(k in q for k in ["schedule", "time", "when"]):
        return "Your briefing is delivered at 8:00 AM every morning in your preferred schedule (daily, weekdays, or weekly)."
    return "StackPulse curates the highest-signal developer updates and security advisories for your exact stack, delivered to your inbox every morning at 8:00 AM."


def ask_assistant(user_message: str) -> str:
    """Query Groq API for a response in under 2 sentences, with graceful fallback."""
    clean_query = (user_message or "").strip()
    if not clean_query:
        return "Feel free to ask me anything about how StackPulse curates your daily developer intelligence!"

    api_key = config.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return _get_fallback_reply(clean_query)

    try:
        client = Groq(api_key=api_key, timeout=2.5, max_retries=0)
        
        last_error = None
        for model in GROQ_MODELS:
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": clean_query},
                    ],
                    max_tokens=90,
                    temperature=0.3,
                )
                text = resp.choices[0].message.content.strip()
                if text:
                    # Enforce max 2 sentences
                    sentences = re.split(r'(?<=[.!?])\s+', text)
                    if len(sentences) > 2:
                        text = " ".join(sentences[:2])
                    return text
            except Exception as e:
                last_error = e
                continue

        log.warning("groq_assistant_all_models_failed", error=str(last_error))
        return _get_fallback_reply(clean_query)

    except Exception as exc:
        log.warning("groq_assistant_exception", error=str(exc))
        return _get_fallback_reply(clean_query)
