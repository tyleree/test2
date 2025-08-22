from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func
from db import Base
import uuid

class Event(Base):
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    type = Column(String(32), index=True)  # 'pageview' | 'chat_question'
    path = Column(Text, nullable=True)     # e.g., '/faq'
    sid = Column(String(64), index=True)   # anonymous session id
    ip = Column(String(64), nullable=True)
    ua = Column(Text, nullable=True)       # user agent
    ref = Column(Text, nullable=True)      # referrer
    meta = Column(Text, nullable=True)     # optional JSON string

# Composite indexes for better query performance
Index("idx_events_type_ts", Event.type, Event.ts.desc())
Index("idx_events_path_ts", Event.path, Event.ts.desc())
