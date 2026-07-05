"""
Compatibility shim: delegate to settings module using pydantic BaseSettings.
Keep this file so existing imports (from config import config) continue to work.
"""
from settings import settings as config

__all__ = ["config"]
