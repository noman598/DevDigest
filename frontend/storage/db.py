
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

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
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