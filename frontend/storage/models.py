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