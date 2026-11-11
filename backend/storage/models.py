import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    ARRAY, Boolean, Column, DateTime, Enum,
    ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import declarative_base, relationship
from pgvector.sqlalchemy import Vector

Base = declarative_base()

class PipelineStatus(str, PyEnum):
    SCRAPED  = "SCRAPED"
    ENRICHED = "ENRICHED"
    EMBEDDED = "EMBEDDED"
    FAILED   = "FAILED"


class IngestionStatus(str, PyEnum):
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class Source(Base):
    __tablename__ = "sources"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name       = Column(String, nullable=False, unique=True)   # "github_trending"
    config     = Column(JSON, default={})                      # language, since, etc.
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now())

    content_items   = relationship("ContentItem",  back_populates="source")
    ingestion_runs  = relationship("IngestionRun", back_populates="source")


class ContentItem(Base):
    __tablename__ = "content_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_external"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id       = Column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    external_id     = Column(String, nullable=False)  # "owner/repo" or article ID
    url             = Column(Text,   nullable=False)
    raw_data        = Column(JSON,   nullable=False)  # full scraped payload
    scraped_at      = Column(DateTime, default=datetime.now())
    pipeline_status = Column(Enum(PipelineStatus), default=PipelineStatus.SCRAPED)
    failure_reason  = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=datetime.now())

    source     = relationship("Source",           back_populates="content_items")
    enrichment = relationship("ContentEnrichment", back_populates="content_item", uselist=False)
    embeddings = relationship("ContentEmbedding",  back_populates="content_item")


class ContentEnrichment(Base):
    """
    LLM-generated metadata. Generic — works for any source (GitHub, HN, blogs).
    Source-specific fields (stars, forks) stay in content_items.raw_data.
    """
    __tablename__ = "content_enrichments"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), unique=True, nullable=False)
    title           = Column(Text)
    summary         = Column(Text)
    tech_stack      = Column(ARRAY(String), default=[])
    topics          = Column(ARRAY(String), default=[])
    use_case        = Column(String)   # library | tool | tutorial | research | framework | other
    enriched_at     = Column(DateTime, default=datetime.now())
    llm_model       = Column(String)

    content_item = relationship("ContentItem", back_populates="enrichment")


class ContentEmbedding(Base):
    """
    One row per (item × embedding_model).
    Unique constraint lets you store both 3-small and 3-large vectors
    for the same item if you want to A/B test.
    """
    __tablename__ = "content_embeddings"
    __table_args__ = (
        UniqueConstraint("content_item_id", "embedding_model", name="uq_item_model"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), nullable=False)
    embedding       = Column(Vector(1536))   # pgvector — change dims if you swap model
    embedding_model = Column(String, nullable=False)
    embedded_text   = Column(Text)           # exact text fed to embedding API — for reproducibility
    created_at      = Column(DateTime, default=datetime.now())

    content_item = relationship("ContentItem", back_populates="embeddings")


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id       = Column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    started_at      = Column(DateTime, default=datetime.now())
    finished_at     = Column(DateTime, nullable=True)
    items_scraped   = Column(Integer, default=0)
    items_new       = Column(Integer, default=0)
    items_enriched  = Column(Integer, default=0)
    items_embedded  = Column(Integer, default=0)
    status          = Column(Enum(IngestionStatus), default=IngestionStatus.RUNNING)
    error_log       = Column(Text, nullable=True)

    source = relationship("Source", back_populates="ingestion_runs")




class UserProfile(Base):
    __tablename__ = "user_profiles"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email               = Column(String, nullable=False, unique=True)
    name                = Column(String, nullable=True)

    selected_sources    = Column(ARRAY(String), default=[])       # ["github_trending", "hacker_news"]
    liked_tags          = Column(ARRAY(String), default=[])
    disliked_tags       = Column(ARRAY(String), default=[])
    custom_interests    = Column(Text, nullable=True)
    keyword_alerts      = Column(Text, nullable=True)

    frequency           = Column(String, default="daily")          # daily | weekly | weekdays
    delivery_time       = Column(String, default="08:00")
    include_summary     = Column(Boolean, default=True)
    include_why_matters = Column(Boolean, default=True)

    is_active           = Column(Boolean, default=True)
    created_at          = Column(DateTime, default=datetime.now)
    updated_at          = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    embedding_status    = Column(String, default="pending")



class UserEmbedding(Base):
    __tablename__ = "user_embeddings"
    __table_args__ = (
        UniqueConstraint("user_id", "embedding_model", name="uq_user_model"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("user_profiles.id"), nullable=False)
    embedding       = Column(Vector(1536))
    embedding_model = Column(String, nullable=False)
    embedded_text   = Column(Text)
    created_at      = Column(DateTime, default=datetime.now)

    user = relationship("UserProfile", backref="embeddings")

class LLMUsageLog(Base):
    __tablename__ = "llm_usage_log"

    id = Column(Integer, primary_key=True)
    provider = Column(String, nullable=False)          # "groq" | "gemini"
    model = Column(String, nullable=False)              # "llama-3.3-70b-versatile"
    operation = Column(String, nullable=False)          # "enrichment" | "digest_generation" | "embedding"

    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    latency_ms = Column(Integer, nullable=True)
    status = Column(String, default="success")          # "success" | "failed"
    error_message = Column(String, nullable=True)

    content_item_id = Column(Integer, nullable=True)     # link back if enrichment
    user_id = Column(Integer, nullable=True)             # link back if digest/embedding

    created_at = Column(DateTime, default=datetime.now)


class UserMemory(Base):
    """
    Long-Term & Episodic Memory for the Personal AI Curator Agent.
    Tracks delivered article IDs (preventing repeats), recent topics (fatigue tracking),
    and evolving notes written by the Agent about the user's technical interests.
    """
    __tablename__ = "user_memories"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id            = Column(UUID(as_uuid=True), ForeignKey("user_profiles.id"), unique=True, nullable=False)
    delivered_history  = Column(JSON, default=list)    # [{"external_id": "...", "title": "...", "delivered_at": "..."}]
    recent_topics      = Column(JSON, default=dict)    # {"Python": 4, "Rust": 2, "LLM": 6} (fatigue tracking)
    agent_notes        = Column(Text, default="")      # Evolving notes by the Agent about user's taste
    last_curated_at    = Column(DateTime, default=datetime.now)
    created_at         = Column(DateTime, default=datetime.now)
    updated_at         = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("UserProfile", backref="memory", uselist=False)
