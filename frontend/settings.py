"""
Pydantic-based settings. Loads from .env using pydantic-settings.
Other modules should import from config (backwards-compatible) or from this module.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM
    ANTHROPIC_API_KEY: str = ""

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
    # Scraper
    GITHUB_TRENDING_LANGUAGE: str = ""
    GITHUB_TRENDING_SINCE: str = "daily"
    USER_AGENT: str = "GitHubDigestBot/1.0 (personal project)"

    # Load environment from .env file, ignoring extra legacy vars
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def validate_required(self):
        """Call this at startup to fail fast if required config is missing."""
        missing = []
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}. "
                f"Copy .env.example to .env and fill it in."
            )


# Singleton instance for easy imports
settings = Settings()
