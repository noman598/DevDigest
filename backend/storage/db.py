
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
from storage.models import Base

# Base = declarative_base()
engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    from storage import models
    Base.metadata.create_all(engine)
    log.info("db_initialized", url=config.DATABASE_URL.split("@")[-1])  # don't log credentials
