"""
Pydantic-based settings. Loads from .env using pydantic-settings.
Other modules should import from config (backwards-compatible) or from this module.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM
    ANTHROPIC_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"

    # Email
    BREVO_API_KEY: str = ""
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = ""
    EMAIL_TO: str = ""
    GROQ_API_KEY: str = ""
    # Database
    DATABASE_URL: str = ''
    COHERE_API_KEY: str = ''
    GEMINI_API_KEY: str = ''

    # LangSmith Observability & Tracing
    LANGSMITH_TRACING: bool = True
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "stackpulse-news"

    # Scraper
    GITHUB_TRENDING_LANGUAGE: str = ""
    GITHUB_TRENDING_SINCE: str = "daily"
    USER_AGENT: str = "StackPulseBot/1.0 (developer digest)"

    # Load environment from .env file, ignoring extra legacy vars
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def validate_required(self):
        """Call this at startup to fail fast if required config is missing."""
        missing = []
        # if not self.ANTHROPIC_API_KEY:
        #     missing.append("ANTHROPIC_API_KEY")
        # if not self.RESEND_API_KEY:
        #     missing.append("RESEND_API_KEY")
        # if not self.EMAIL_FROM:
        #     missing.append("EMAIL_FROM")
        # if not self.EMAIL_TO:
        #     missing.append("EMAIL_TO")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Copy .env.example to .env and fill it in."
            )


import os

# Singleton instance for easy imports
settings = Settings()

# Automatically configure LangSmith environment variables for LangChain / LangGraph tracing
if settings.LANGSMITH_API_KEY:
    tracing_enabled = "true" if settings.LANGSMITH_TRACING else "false"
    os.environ["LANGSMITH_TRACING"] = tracing_enabled
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
    os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    # Compatibility with LANGCHAIN_ env keys
    os.environ["LANGCHAIN_TRACING_V2"] = tracing_enabled
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
