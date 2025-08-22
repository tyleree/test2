import os
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker, declarative_base

def _normalize(url: str) -> str:
    """Normalize postgres:// to postgresql+psycopg:// for SQLAlchemy 2.0+"""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url

DATABASE_URL = _normalize(os.getenv("DATABASE_URL", ""))
engine = create_engine(DATABASE_URL, pool_pre_ping=True) if DATABASE_URL else None
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False)) if engine else None
Base = declarative_base()
