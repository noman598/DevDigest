"""
Pydantic-based settings. Loads from .env using pydantic-settings.
Other modules should import from config (backwards-compatible) or from this module.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # LLM
    ANTHROPIC_API_KEY: str = ""

    # Email
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = ""
    EMAIL_TO: str = ""
    GROQ_API_KEY: str = ""
    # Database
    DATABASE_URL: str = ''

    # Scraper
    GITHUB_TRENDING_LANGUAGE: str = ""
    GITHUB_TRENDING_SINCE: str = "daily"
    USER_AGENT: str = "GitHubDigestBot/1.0 (personal project)"

    # Load environment from .env file
    model_config = SettingsConfigDict(env_file=".env")

    def validate_required(self):  # was: def validate(self)
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


# Singleton instance for easy imports
settings = Settings()
