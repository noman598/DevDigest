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

from scrapers.base import RawItem
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


def save_items(items: List[RawItem]) -> List[RawItem]:
    """
    Upserts items. Returns only the items that were NEWLY inserted
    (not seen before) — these are what should go in today's digest.
    Uses Postgres' native ON CONFLICT DO NOTHING for atomic, race-safe dedup.
    """
    if not items:
        return []

    new_items = []
    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        for item in items:
            stmt = pg_insert(Item).values(
                source=item.source,
                title=item.title,
                url=item.url,
                description=item.description,
                item_metadata=json.dumps(item.metadata),
                scraped_at=now,
            ).on_conflict_do_nothing(constraint="uq_source_url")

            result = session.execute(stmt)
            session.commit()

            # rowcount == 1 means it was actually inserted (not a conflict skip)
            if result.rowcount > 0:
                new_items.append(item)

    log.info("items_saved", new=len(new_items), total_scraped=len(items))
    return new_items

def save_items_dev(items: List[RawItem]) -> List[RawItem]:
    """
    DEV ONLY — plain insert with no dedup, so you can re-run multiple times
    and always get data through the pipeline.
    """
    if not items:
        return []

    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        for item in items:
            stmt = pg_insert(Item).values(
                source=item.source,
                title=item.title,
                url=item.url,
                description=item.description,
                item_metadata=json.dumps(item.metadata),
                scraped_at=now,
            )
            session.execute(stmt)
        session.commit()

    log.info("items_saved_dev", total=len(items))
    return items  # return everything as "new" so the full pipeline runs

def get_items_last_24h(source: str = None):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    with SessionLocal() as session:
        query = session.query(Item).filter(Item.scraped_at >= cutoff)
        if source:
            query = query.filter(Item.source == source)
        rows = query.order_by(Item.scraped_at.desc()).all()

        # Return plain dicts so callers don't depend on SQLAlchemy objects
        # staying attached to a session (avoids DetachedInstanceError later)
        return [
            {
                "id": r.id,
                "source": r.source,
                "title": r.title,
                "url": r.url,
                "description": r.description,
                "metadata": json.loads(r.item_metadata) if r.item_metadata else {},
                "scraped_at": r.scraped_at,
            }
            for r in rows
        ]


def was_digest_sent_today(sent_to: str) -> bool:
    """Idempotency check: prevents double-sending if main.py runs twice in one day."""
    today = datetime.now(timezone.utc).date().isoformat()
    with SessionLocal() as session:
        exists = (
            session.query(DigestLog)
            .filter(DigestLog.digest_date == today, DigestLog.sent_to == sent_to)
            .first()
        )
        return exists is not None


def log_digest_sent(sent_to: str, item_count: int):
    today = datetime.now(timezone.utc).date().isoformat()
    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        stmt = pg_insert(DigestLog).values(
            digest_date=today,
            sent_to=sent_to,
            item_count=item_count,
            sent_at=now,
        ).on_conflict_do_nothing(constraint="uq_date_recipient")
        session.execute(stmt)
        session.commit()


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