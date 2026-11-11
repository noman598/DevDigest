
import json
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, UniqueConstraint,Boolean, JSON, func 
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

from storage.models import UserProfile

# from scrapers.base import RawItem
from config import config
from utils.logger import log
from storage.models import Base

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 3})
SessionLocal = sessionmaker(bind=engine)

def init_db():
    from storage import models
    Base.metadata.create_all(engine)
    log.info("db_initialized", url=config.DATABASE_URL.split("@")[-1])  # don't log credentials



def save_user_email(email: str) -> bool:
    """
    Save user email to database.
    
    Args:
        email: User's email address
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not email:
        return False
    
    email = email.lower().strip()
    
    try:
        with SessionLocal() as session:
            # Check if user exists
            existing = session.query(UserProfile).filter(UserProfile.email == email).first()
            
            if existing:
                # Already exists, return True
                log.info("user_already_exists", email=email)
                return True
            
            # Create new user
            new_user = UserProfile(email=email)
            session.add(new_user)
            session.commit()
            log.info("user_email_saved", email=email)
            return True
            
    except Exception as e:
        log.error("save_user_email_error", email=email, error=str(e))
        return False
    



def save_user_profile(form_data: dict) -> bool:
    """
    Upsert user profile — insert new, or update existing row if email
    already exists (re-submitting the wizard updates preferences).
    """
    email = form_data.get("email", "").lower().strip()
    if not email:
        return False

    try:
        with SessionLocal() as session:
            stmt = pg_insert(UserProfile).values(
                email               = email,
                name                = form_data.get("name", ""),
                selected_sources    = form_data.get("selected_sources", []),
                liked_tags          = form_data.get("liked_tags", []),
                disliked_tags       = form_data.get("disliked_tags", []),
                custom_interests    = form_data.get("custom_interests", ""),
                keyword_alerts      = form_data.get("keyword_alerts", ""),
                frequency           = form_data.get("frequency", "daily"),
                delivery_time       = form_data.get("delivery_time", "08:00"),
                include_summary     = form_data.get("include_summary", True),
                include_why_matters = form_data.get("include_why_matters", True),
            ).on_conflict_do_update(
                index_elements=["email"],
                set_={
                    "name":                form_data.get("name", ""),
                    "selected_sources":    form_data.get("selected_sources", []),
                    "liked_tags":          form_data.get("liked_tags", []),
                    "disliked_tags":       form_data.get("disliked_tags", []),
                    "custom_interests":    form_data.get("custom_interests", ""),
                    "keyword_alerts":      form_data.get("keyword_alerts", ""),
                    "frequency":           form_data.get("frequency", "daily"),
                    "delivery_time":       form_data.get("delivery_time", "08:00"),
                    "include_summary":     form_data.get("include_summary", True),
                    "include_why_matters": form_data.get("include_why_matters", True),
                    "embedding_status":    "pending",
                    "updated_at":          datetime.now(),
                },
            )
            session.execute(stmt)
            session.commit()
            log.info("user_profile_saved", email=email)
            return True

    except Exception as e:
        log.error("save_user_profile_error", email=email, error=str(e))
        return False


def user_exists(email: str) -> bool:
    with SessionLocal() as session:
        return session.query(UserProfile).filter(UserProfile.email == email.lower().strip()).first() is not None


def get_user_profile(email: str):
    """Retrieve existing user profile data as a dict for form pre-population."""
    if not email:
        return None
    try:
        with SessionLocal() as session:
            user = session.query(UserProfile).filter(UserProfile.email == email.lower().strip()).first()
            if not user:
                return None
            return {
                "email": user.email,
                "name": user.name or "",
                "selected_sources": user.selected_sources or ["github_trending", "openai_news", "anthropic_news", "hacker_news"],
                "liked_tags": user.liked_tags or [],
                "disliked_tags": user.disliked_tags or [],
                "custom_interests": user.custom_interests or "",
                "keyword_alerts": user.keyword_alerts or "",
                "frequency": user.frequency or "daily",
                "delivery_time": user.delivery_time or "08:00",
                "include_summary": bool(user.include_summary),
                "include_why_matters": bool(user.include_why_matters),
                "embedding_status": user.embedding_status or "pending",
            }
    except Exception as e:
        log.error("get_user_profile_error", email=email, error=str(e))
        return None


_stats_cache = None
_stats_cache_time = 0.0

def get_platform_stats():
    """Retrieve high-level system metrics for dashboard view with 60s cache."""
    global _stats_cache, _stats_cache_time
    import time
    now = time.time()
    if _stats_cache and (now - _stats_cache_time) < 60.0:
        return _stats_cache

    try:
        with SessionLocal() as session:
            from sqlalchemy import text
            row = session.execute(text("""
                SELECT
                    (SELECT count(*) FROM user_profiles WHERE is_active = true) as active_users,
                    (SELECT count(*) FROM user_profiles WHERE embedding_status = 'embedded') as embedded_users,
                    (SELECT count(*) FROM content_items WHERE pipeline_status = 'EMBEDDED') as embedded_items,
                    (SELECT count(*) FROM sources WHERE is_active = true) as active_sources
            """)).first()
            if row:
                _stats_cache = {
                    "active_users": row.active_users or 0,
                    "embedded_users": row.embedded_users or 0,
                    "embedded_items": row.embedded_items or 0,
                    "active_sources": row.active_sources or 0,
                }
                _stats_cache_time = now
                return _stats_cache
    except Exception as e:
        log.warning("get_platform_stats_error", error=str(e))

    fallback = {
        "active_users": 1,
        "embedded_users": 1,
        "embedded_items": 55,
        "active_sources": 5,
    }
    _stats_cache = fallback
    _stats_cache_time = now
    return fallback