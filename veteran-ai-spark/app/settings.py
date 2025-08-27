"""
Configuration settings for the FastAPI RAG pipeline.
Uses pydantic-settings for environment variable management.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import validator


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # OpenAI Configuration
    openai_api_key: str
    
    # Pinecone Configuration
    pinecone_api_key: str
    pinecone_env: str
    pinecone_index: str
    
    # Model Configuration
    model_big: str = "gpt-4o"
    model_small: str = "gpt-4o-mini"
    
    # Cache Configuration
    cache_db_path: str = "data/cache.sqlite"
    faiss_path: str = "data/query_cache.faiss"
    
    # Similarity Thresholds (tuneable defaults)
    sim_threshold: float = 0.92  # cosine similarity for semantic hits
    doc_overlap_min: float = 0.6  # Jaccard overlap top_doc_ids vs cached
    max_sources: int = 6
    retrieve_k: int = 50
    rerank_k: int = 8
    compress_budget_tokens: int = 2200
    
    # Document Version Control
    doc_version_salt: str = "v1.0.0"
    
    # Cache Embedding Model
    cache_embedding_model: str = "all-MiniLM-L6-v2"
    
    # Admin Configuration
    admin_token: Optional[str] = None
    
    @validator('cache_db_path', 'faiss_path')
    def ensure_data_dir(cls, v):
        """Ensure data directory exists for cache files."""
        os.makedirs(os.path.dirname(v), exist_ok=True)
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Convert environment variable names to lowercase
        case_sensitive = False


# Global settings instance
settings = Settings()

