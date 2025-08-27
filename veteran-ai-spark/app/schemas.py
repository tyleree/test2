"""
Pydantic schemas for request/response models.
"""

from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Request schema for asking a question."""
    question: str = Field(..., min_length=1, max_length=2000, description="The question to ask")
    detail: Optional[str] = Field(None, description="Detail level: 'more' for expanded context")


class Citation(BaseModel):
    """Citation information for a source."""
    n: int = Field(..., description="Citation number")
    url: str = Field(..., description="Source URL")


class TokenUsage(BaseModel):
    """Token usage information."""
    model_big: str
    model_small: str
    tokens_big: int = 0
    tokens_small: int = 0
    total_tokens: int = 0
    saved_tokens_estimate: int = 0


class AnswerPayload(BaseModel):
    """Response schema for answer endpoint."""
    answer: str = Field(..., description="The generated answer")
    citations: List[Citation] = Field(default_factory=list, description="Source citations")
    cache_mode: Literal["miss", "exact", "semantic"] = Field(..., description="Cache hit type")
    token_usage: TokenUsage = Field(..., description="Token consumption details")
    latency_ms: int = Field(..., description="Response latency in milliseconds")


class CacheStats(BaseModel):
    """Cache statistics."""
    total_entries: int
    exact_hits: int
    semantic_hits: int
    misses: int
    hit_rate: float
    memory_usage_mb: float


class CacheStatsResponse(BaseModel):
    """Response schema for cache stats."""
    stats: CacheStats
    status: str = "ok"


class ClearCacheRequest(BaseModel):
    """Request schema for clearing cache."""
    confirm: bool = Field(..., description="Confirmation flag")


class ClearCacheResponse(BaseModel):
    """Response schema for clearing cache."""
    cleared: bool
    entries_removed: int
    status: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = "1.0.0"
    cache_db_exists: bool
    faiss_index_exists: bool


class MetricsData(BaseModel):
    """Metrics data for monitoring."""
    cache_hit_ratio: float
    avg_latency_ms: float
    tokens_saved_estimate: int
    total_requests: int
    exact_cache_hits: int
    semantic_cache_hits: int
    cache_misses: int
    model_usage: Dict[str, int]


class CompressedPack(BaseModel):
    """Compressed context pack."""
    quotes: List[Dict[str, Any]]
    sources: List[Dict[str, str]]
    top_doc_ids: List[str]


class CacheEntry(BaseModel):
    """Cache entry data model."""
    id: Optional[int] = None
    normalized: str
    q_hash: str
    answer: str
    citations_json: str
    compressed_pack_json: str
    top_doc_ids_json: str
    token_cost_json: str
    model_big: str
    model_small: str
    doc_version_hash: str
    created_at: Optional[str] = None
    last_hit_at: Optional[str] = None
    hits: int = 0










