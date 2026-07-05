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
    SCRAPED  = "scraped"
    ENRICHED = "enriched"
    EMBEDDED = "embedded"
    FAILED   = "failed"


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
