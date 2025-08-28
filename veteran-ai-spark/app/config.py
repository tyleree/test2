"""
Configuration management for RAG Flask application.
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv('env.txt')  # For compatibility with existing setup
load_dotenv('.env')

class Config(BaseSettings):
    """Application configuration with validation."""
    
    # OpenAI Configuration
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    model_big: str = Field("gpt-4o", env="MODEL_BIG")
    model_small: str = Field("gpt-4o-mini", env="MODEL_SMALL")
    embed_model: str = Field("text-embedding-3-small", env="EMBED_MODEL")
    
    # Pinecone Configuration
    pinecone_api_key: str = Field(..., env="PINECONE_API_KEY")
    pinecone_index: str = Field("veteran-rag", env="PINECONE_INDEX")
    pinecone_namespace: str = Field("production", env="PINECONE_NAMESPACE")
    
    # Flask Configuration
    flask_env: str = Field("production", env="FLASK_ENV")
    secret_key: str = Field(..., env="SECRET_KEY")
    debug: bool = Field(False, env="DEBUG")
    
    # RAG Configuration
    retrieval_top_k: int = Field(50, env="RETRIEVAL_TOP_K")
    rerank_top_k: int = Field(8, env="RERANK_TOP_K")
    compress_budget_tokens: int = Field(2200, env="COMPRESS_BUDGET_TOKENS")
    max_quotes: int = Field(6, env="MAX_QUOTES")
    quote_max_tokens: int = Field(120, env="QUOTE_MAX_TOKENS")
    
    # Cache Configuration
    cache_db_path: str = Field("cache.db", env="CACHE_DB_PATH")
    semantic_threshold: float = Field(0.92, env="SEMANTIC_THRESHOLD")
    jaccard_threshold: float = Field(0.6, env="JACCARD_THRESHOLD")
    doc_version_salt: str = Field("v1.0", env="DOC_VERSION_SALT")
    
    # Evaluation
    eval_qas_path: str = Field("app/eval/qas.csv", env="EVAL_QAS_PATH")
    
    # Deployment
    port: int = Field(5000, env="PORT")
    workers: int = Field(2, env="WORKERS")
    threads: int = Field(4, env="THREADS")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global configuration instance
config = Config()

# Validation
def validate_config() -> None:
    """Validate critical configuration values."""
    required_keys = [
        config.openai_api_key,
        config.pinecone_api_key,
        config.secret_key
    ]
    
    if not all(required_keys):
        raise ValueError("Missing required environment variables. Check OPENAI_API_KEY, PINECONE_API_KEY, SECRET_KEY")
    
    if config.semantic_threshold < 0.8 or config.semantic_threshold > 1.0:
        raise ValueError("SEMANTIC_THRESHOLD must be between 0.8 and 1.0")
    
    if config.jaccard_threshold < 0.3 or config.jaccard_threshold > 1.0:
        raise ValueError("JACCARD_THRESHOLD must be between 0.3 and 1.0")

# Validate on import
validate_config()

