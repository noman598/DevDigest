"""
Storage layer — PostgreSQL via SQLAlchemy.

Same public function signatures as the old SQLite version (save_items,
get_items_last_24h, was_digest_sent_today, log_digest_sent, init_db) —
this is the whole point of isolating storage behind a module: main.py
and every other caller didn't need to change at all for this swap.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, UniqueConstraint,Boolean, JSON, func 
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

# from scrapers.base import RawItem
from config import config
from utils.logger import log

Base = declarative_base()
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    description = Column(Text)
    item_metadata = Column(Text)  # JSON-encoded string
    scraped_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("source", "url", name="uq_source_url"),)


class DigestLog(Base):
    __tablename__ = "digest_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    digest_date = Column(String, nullable=False)  # ISO date string, e.g. "2026-06-21"
    sent_to = Column(String, nullable=False)
    item_count = Column(Integer, nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (UniqueConstraint("digest_date", "sent_to", name="uq_date_recipient"),)

class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)

def init_db():
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