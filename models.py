from sqlalchemy import Column, Integer, String, Text, DateTime, Index, Float
from sqlalchemy.sql import func
from db import Base
import uuid

class Event(Base):
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    type = Column(String(32), index=True)  # 'pageview' | 'chat_question' | 'visitor_location'
    path = Column(Text, nullable=True)     # e.g., '/faq'
    sid = Column(String(64), index=True)   # anonymous session id
    ip = Column(String(64), nullable=True)
    ua = Column(Text, nullable=True)       # user agent
    ref = Column(Text, nullable=True)      # referrer
    meta = Column(Text, nullable=True)     # optional JSON string
    
    # Location tracking fields
    location = Column(String(64), nullable=True)  # state code, 'International-XX', 'Local', 'Unknown'
    country = Column(String(8), nullable=True)    # country code
    lat = Column(Float, nullable=True)            # latitude (for future use)
    lng = Column(Float, nullable=True)            # longitude (for future use)

# Composite indexes for better query performance
Index("idx_events_type_ts", Event.type, Event.ts.desc())
Index("idx_events_path_ts", Event.path, Event.ts.desc())
Index("idx_events_location", Event.location)

class LegacyStats(Base):
    """Table to store migrated file-based stats for historical continuity"""
    __tablename__ = "legacy_stats"
    
    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, index=True)  # e.g., 'ask_count', 'visit_count'
    value = Column(Text)  # JSON string for complex values
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
