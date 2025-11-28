"""
Response Caching for RAG Pipeline

Implements two-level caching:
1. Exact cache: Normalized query string -> cached response
2. Semantic cache: Query embedding similarity -> cached response (catches paraphrases)

Features:
- File-backed persistence (survives restarts)
- TTL-based expiration
- Compression for storage efficiency
- Cache hit/miss metrics
"""

import os
import json
import time
import zlib
import hashlib
import threading
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
from pathlib import Path
import re

# Configuration
CACHE_DIR = "data/response_cache"
EXACT_CACHE_FILE = "exact_cache.json"
SEMANTIC_CACHE_FILE = "semantic_cache.json"
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours
SEMANTIC_SIMILARITY_THRESHOLD = 0.92  # High threshold to avoid false matches
MAX_CACHE_ENTRIES = 5000
COMPRESS_RESPONSES = True


@dataclass
class CacheEntry:
    """A cached response entry."""
    query: str
    response: str
    sources: List[Dict[str, Any]]
    model_used: str
    created_at: float
    ttl: float = CACHE_TTL_SECONDS
    hit_count: int = 0
    
    def is_expired(self) -> bool:
        return time.time() > (self.created_at + self.ttl)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "response": self.response,
            "sources": self.sources,
            "model_used": self.model_used,
            "created_at": self.created_at,
            "ttl": self.ttl,
            "hit_count": self.hit_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        return cls(
            query=data["query"],
            response=data["response"],
            sources=data.get("sources", []),
            model_used=data.get("model_used", "unknown"),
            created_at=data["created_at"],
            ttl=data.get("ttl", CACHE_TTL_SECONDS),
            hit_count=data.get("hit_count", 0)
        )


@dataclass
class SemanticCacheEntry(CacheEntry):
    """A semantic cache entry with embedding."""
    embedding: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        # Compress embedding for storage
        if COMPRESS_RESPONSES and self.embedding:
            data["embedding_compressed"] = compress_embedding(self.embedding)
        else:
            data["embedding"] = self.embedding
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemanticCacheEntry":
        embedding = data.get("embedding", [])
        if "embedding_compressed" in data:
            embedding = decompress_embedding(data["embedding_compressed"])
        
        return cls(
            query=data["query"],
            response=data["response"],
            sources=data.get("sources", []),
            model_used=data.get("model_used", "unknown"),
            created_at=data["created_at"],
            ttl=data.get("ttl", CACHE_TTL_SECONDS),
            hit_count=data.get("hit_count", 0),
            embedding=embedding
        )


@dataclass
class CacheMetrics:
    """Track cache performance."""
    exact_hits: int = 0
    exact_misses: int = 0
    semantic_hits: int = 0
    semantic_misses: int = 0
    
    @property
    def total_hits(self) -> int:
        return self.exact_hits + self.semantic_hits
    
    @property
    def total_requests(self) -> int:
        return self.exact_hits + self.exact_misses
    
    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_hits / self.total_requests
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "exact_hits": self.exact_hits,
            "exact_misses": self.exact_misses,
            "semantic_hits": self.semantic_hits,
            "semantic_misses": self.semantic_misses,
            "total_hits": self.total_hits,
            "hit_rate": f"{self.hit_rate:.2%}"
        }


def normalize_query(query: str) -> str:
    """
    Normalize a query for exact matching.
    - Lowercase
    - Strip whitespace
    - Remove punctuation
    - Collapse multiple spaces
    """
    query = query.lower().strip()
    query = re.sub(r'[^\w\s]', '', query)
    query = re.sub(r'\s+', ' ', query)
    return query


def query_hash(query: str) -> str:
    """Generate a hash key for a normalized query."""
    return hashlib.sha256(normalize_query(query).encode()).hexdigest()[:16]


def compress_embedding(embedding: List[float]) -> str:
    """Compress an embedding for storage."""
    json_bytes = json.dumps(embedding).encode('utf-8')
    compressed = zlib.compress(json_bytes, level=6)
    return compressed.hex()


def decompress_embedding(hex_data: str) -> List[float]:
    """Decompress a stored embedding."""
    compressed = bytes.fromhex(hex_data)
    json_bytes = zlib.decompress(compressed)
    return json.loads(json_bytes.decode('utf-8'))


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


class ResponseCache:
    """
    Two-level response cache with exact and semantic matching.
    
    Usage:
        cache = ResponseCache()
        cache.load()
        
        # Check cache
        cached = cache.get(query, query_embedding)
        if cached:
            return cached  # Fast path
        
        # Generate response...
        
        # Store in cache
        cache.set(query, response, sources, model_used, query_embedding)
    """
    
    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self.exact_cache: Dict[str, CacheEntry] = {}
        self.semantic_cache: List[SemanticCacheEntry] = []
        self.metrics = CacheMetrics()
        self._lock = threading.Lock()
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize cache directory and load existing cache."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.load()
        self._initialized = True
        print(f"[CACHE] Initialized with {len(self.exact_cache)} exact entries, {len(self.semantic_cache)} semantic entries")
    
    def load(self) -> None:
        """Load cache from disk."""
        # Load exact cache
        exact_path = self.cache_dir / EXACT_CACHE_FILE
        if exact_path.exists():
            try:
                with open(exact_path, 'r') as f:
                    data = json.load(f)
                for key, entry_data in data.items():
                    entry = CacheEntry.from_dict(entry_data)
                    if not entry.is_expired():
                        self.exact_cache[key] = entry
                print(f"[CACHE] Loaded {len(self.exact_cache)} exact cache entries")
            except Exception as e:
                print(f"[CACHE] Error loading exact cache: {e}")
        
        # Load semantic cache
        semantic_path = self.cache_dir / SEMANTIC_CACHE_FILE
        if semantic_path.exists():
            try:
                with open(semantic_path, 'r') as f:
                    data = json.load(f)
                for entry_data in data:
                    entry = SemanticCacheEntry.from_dict(entry_data)
                    if not entry.is_expired():
                        self.semantic_cache.append(entry)
                print(f"[CACHE] Loaded {len(self.semantic_cache)} semantic cache entries")
            except Exception as e:
                print(f"[CACHE] Error loading semantic cache: {e}")
    
    def save(self) -> None:
        """Save cache to disk."""
        with self._lock:
            # Save exact cache
            exact_path = self.cache_dir / EXACT_CACHE_FILE
            exact_data = {k: v.to_dict() for k, v in self.exact_cache.items() if not v.is_expired()}
            with open(exact_path, 'w') as f:
                json.dump(exact_data, f)
            
            # Save semantic cache
            semantic_path = self.cache_dir / SEMANTIC_CACHE_FILE
            semantic_data = [e.to_dict() for e in self.semantic_cache if not e.is_expired()]
            with open(semantic_path, 'w') as f:
                json.dump(semantic_data, f)
    
    def get(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None
    ) -> Optional[Tuple[str, List[Dict[str, Any]], str, str]]:
        """
        Get a cached response.
        
        Args:
            query: The user query
            query_embedding: Optional query embedding for semantic matching
            
        Returns:
            Tuple of (response, sources, model_used, cache_type) or None
        """
        key = query_hash(query)
        
        with self._lock:
            # Try exact match first
            if key in self.exact_cache:
                entry = self.exact_cache[key]
                if not entry.is_expired():
                    entry.hit_count += 1
                    self.metrics.exact_hits += 1
                    print(f"[CACHE] Exact hit for query: {query[:50]}...")
                    return (entry.response, entry.sources, entry.model_used, "exact")
                else:
                    del self.exact_cache[key]
            
            self.metrics.exact_misses += 1
            
            # Try semantic match if embedding provided
            if query_embedding and self.semantic_cache:
                best_match = None
                best_score = 0.0
                
                for entry in self.semantic_cache:
                    if entry.is_expired():
                        continue
                    
                    score = cosine_similarity(query_embedding, entry.embedding)
                    if score > best_score and score >= SEMANTIC_SIMILARITY_THRESHOLD:
                        best_score = score
                        best_match = entry
                
                if best_match:
                    best_match.hit_count += 1
                    self.metrics.semantic_hits += 1
                    print(f"[CACHE] Semantic hit (score={best_score:.3f}) for query: {query[:50]}...")
                    return (best_match.response, best_match.sources, best_match.model_used, "semantic")
                
                self.metrics.semantic_misses += 1
        
        return None
    
    def set(
        self,
        query: str,
        response: str,
        sources: List[Dict[str, Any]],
        model_used: str,
        query_embedding: Optional[List[float]] = None,
        ttl: float = CACHE_TTL_SECONDS
    ) -> None:
        """
        Store a response in cache.
        
        Args:
            query: The user query
            response: The generated response
            sources: List of source documents
            model_used: Model that generated the response
            query_embedding: Optional query embedding for semantic caching
            ttl: Time to live in seconds
        """
        key = query_hash(query)
        
        with self._lock:
            # Add to exact cache
            self.exact_cache[key] = CacheEntry(
                query=query,
                response=response,
                sources=sources,
                model_used=model_used,
                created_at=time.time(),
                ttl=ttl
            )
            
            # Add to semantic cache if embedding provided
            if query_embedding:
                self.semantic_cache.append(SemanticCacheEntry(
                    query=query,
                    response=response,
                    sources=sources,
                    model_used=model_used,
                    created_at=time.time(),
                    ttl=ttl,
                    embedding=query_embedding
                ))
            
            # Evict old entries if cache is too large
            self._evict_if_needed()
        
        # Save periodically (every 10 new entries)
        if (len(self.exact_cache) % 10) == 0:
            self.save()
    
    def _evict_if_needed(self) -> None:
        """Evict old entries if cache exceeds max size."""
        # Evict expired entries first
        self.exact_cache = {k: v for k, v in self.exact_cache.items() if not v.is_expired()}
        self.semantic_cache = [e for e in self.semantic_cache if not e.is_expired()]
        
        # If still too large, evict least recently used
        if len(self.exact_cache) > MAX_CACHE_ENTRIES:
            sorted_entries = sorted(
                self.exact_cache.items(),
                key=lambda x: (x[1].hit_count, x[1].created_at)
            )
            entries_to_remove = len(self.exact_cache) - MAX_CACHE_ENTRIES
            for key, _ in sorted_entries[:entries_to_remove]:
                del self.exact_cache[key]
        
        if len(self.semantic_cache) > MAX_CACHE_ENTRIES:
            self.semantic_cache.sort(key=lambda x: (x.hit_count, x.created_at))
            self.semantic_cache = self.semantic_cache[-MAX_CACHE_ENTRIES:]
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self.exact_cache.clear()
            self.semantic_cache.clear()
            self.metrics = CacheMetrics()
        self.save()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics."""
        return {
            **self.metrics.to_dict(),
            "exact_cache_size": len(self.exact_cache),
            "semantic_cache_size": len(self.semantic_cache)
        }


# Global cache instance
_cache: Optional[ResponseCache] = None


def get_response_cache() -> ResponseCache:
    """Get or create the global response cache."""
    global _cache
    if _cache is None:
        _cache = ResponseCache()
        _cache.initialize()
    return _cache


def cache_response(
    query: str,
    response: str,
    sources: List[Dict[str, Any]],
    model_used: str,
    query_embedding: Optional[List[float]] = None
) -> None:
    """Convenience function to cache a response."""
    cache = get_response_cache()
    cache.set(query, response, sources, model_used, query_embedding)


def get_cached_response(
    query: str,
    query_embedding: Optional[List[float]] = None
) -> Optional[Tuple[str, List[Dict[str, Any]], str, str]]:
    """Convenience function to get a cached response."""
    cache = get_response_cache()
    return cache.get(query, query_embedding)

