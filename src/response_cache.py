"""
Response Caching for RAG Pipeline with PostgreSQL Persistence

Implements two-level caching:
1. L1 (In-memory): Fast runtime cache
2. L2 (PostgreSQL): Persistent cache that survives restarts

Features:
- Database-backed persistence (survives Render restarts!)
- In-memory cache for sub-millisecond reads
- Exact matching via query hash
- Semantic matching via embedding similarity
- TTL-based expiration
- Automatic cache warming from database on startup
- LRU eviction for memory management
"""

import os
import json
import time
import zlib
import hashlib
import threading
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re

# Configuration
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours
SEMANTIC_SIMILARITY_THRESHOLD = 0.92  # High threshold to avoid false matches
MAX_MEMORY_CACHE_ENTRIES = 1000  # In-memory limit (PostgreSQL can hold more)
MAX_DB_CACHE_ENTRIES = 10000  # Database limit
COMPRESS_EMBEDDINGS = True

# Check if database is available
def _get_db_available():
    """Check if DATABASE_URL is configured."""
    return bool(os.getenv("DATABASE_URL"))

DB_AVAILABLE = _get_db_available()


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
    embedding: Optional[List[float]] = None
    
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


@dataclass
class CacheMetrics:
    """Track cache performance."""
    exact_hits: int = 0
    exact_misses: int = 0
    semantic_hits: int = 0
    semantic_misses: int = 0
    db_hits: int = 0
    db_writes: int = 0
    db_errors: int = 0
    topic_hits: int = 0  # New: topic graph hits
    
    @property
    def total_hits(self) -> int:
        return self.exact_hits + self.semantic_hits + self.db_hits + self.topic_hits
    
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
            "db_hits": self.db_hits,
            "db_writes": self.db_writes,
            "db_errors": self.db_errors,
            "topic_hits": self.topic_hits,
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
    return hashlib.sha256(normalize_query(query).encode()).hexdigest()[:32]


def compress_embedding(embedding: List[float]) -> str:
    """Compress an embedding for storage."""
    json_bytes = json.dumps(embedding).encode('utf-8')
    compressed = zlib.compress(json_bytes, level=6)
    return compressed.hex()


def decompress_embedding(hex_data: str) -> List[float]:
    """Decompress a stored embedding."""
    try:
        compressed = bytes.fromhex(hex_data)
        json_bytes = zlib.decompress(compressed)
        return json.loads(json_bytes.decode('utf-8'))
    except Exception:
        return []


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
    Two-level response cache with PostgreSQL persistence.
    
    Architecture:
    - L1: In-memory dict for instant reads
    - L2: PostgreSQL for persistence across restarts
    
    On startup:
    1. Warm L1 cache from PostgreSQL (most recent entries)
    
    On cache get:
    1. Check L1 (memory) - instant
    2. If miss, check L2 (PostgreSQL) - ~5ms
    3. Promote L2 hit to L1
    
    On cache set:
    1. Write to L1 (memory)
    2. Async write to L2 (PostgreSQL)
    """
    
    def __init__(self):
        self.memory_cache: Dict[str, CacheEntry] = {}
        self.semantic_entries: List[CacheEntry] = []  # For semantic search
        self.metrics = CacheMetrics()
        self._lock = threading.Lock()
        self._initialized = False
        self._db_session = None
    
    def initialize(self, corpus_hash: Optional[str] = None) -> None:
        """
        Initialize cache and warm from database.
        
        Args:
            corpus_hash: Hash of the current corpus. If different from stored hash,
                        cache will be automatically invalidated to prevent stale answers.
        """
        if self._initialized:
            return
            
        self._initialized = True
        
        if DB_AVAILABLE:
            # Check if corpus has changed - if so, clear cache to prevent stale answers
            if corpus_hash:
                self._check_and_invalidate_on_corpus_change(corpus_hash)
            self._warm_from_database()
        else:
            print("[CACHE] No database - using in-memory cache only")
        
        print(f"[CACHE] Initialized with {len(self.memory_cache)} exact entries, {len(self.semantic_entries)} semantic entries")
    
    def _check_and_invalidate_on_corpus_change(self, corpus_hash: str) -> None:
        """
        Check if corpus has changed and invalidate cache if so.
        
        This prevents stale cached answers from being returned when new content
        is added to the corpus.
        """
        session = self._get_db_session()
        if not session:
            return
            
        try:
            from sqlalchemy import text
            
            # Create metadata table if it doesn't exist
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key VARCHAR(64) PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            session.commit()
            
            # Check stored corpus hash
            result = session.execute(text("""
                SELECT value FROM cache_metadata WHERE key = 'corpus_hash'
            """)).scalar()
            
            if result != corpus_hash:
                # Corpus has changed! Clear the cache
                print(f"[CACHE] Corpus changed (stored: {result}, current: {corpus_hash})")
                print("[CACHE] Clearing stale cache entries...")
                
                # Clear cached_responses table
                session.execute(text("DELETE FROM cached_responses"))
                
                # Also clear topic graph edges to prevent stale topic-based cache hits
                # These link questions to topics and would return old answers
                try:
                    session.execute(text("DELETE FROM question_topics"))
                    session.execute(text("DELETE FROM question_entities"))
                    session.execute(text("DELETE FROM question_sources"))
                    print("[CACHE] Cleared topic graph edges (question_topics, question_entities, question_sources)")
                except Exception as e:
                    print(f"[CACHE] Note: Could not clear topic graph edges: {e}")
                
                # Update stored hash
                session.execute(text("""
                    INSERT INTO cache_metadata (key, value, updated_at) 
                    VALUES ('corpus_hash', :hash, NOW())
                    ON CONFLICT (key) DO UPDATE SET value = :hash, updated_at = NOW()
                """), {"hash": corpus_hash})
                
                session.commit()
                print(f"[CACHE] Cache cleared and corpus hash updated to: {corpus_hash}")
            else:
                print(f"[CACHE] Corpus unchanged (hash: {corpus_hash[:8]}...)")
                
        except Exception as e:
            print(f"[CACHE] Corpus hash check error: {e}")
            session.rollback()
        finally:
            session.close()
    
    def _get_db_session(self):
        """Get a database session."""
        try:
            from db import SessionLocal
            if SessionLocal:
                return SessionLocal()
        except Exception as e:
            print(f"[CACHE] Database session error: {e}")
        return None
    
    def _warm_from_database(self) -> None:
        """Load recent cache entries from PostgreSQL into memory."""
        session = self._get_db_session()
        if not session:
            return
            
        try:
            from sqlalchemy import text
            
            # Check if table exists first
            result = session.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'cached_responses'
                )
            """)).scalar()
            
            if not result:
                print("[CACHE] Creating cached_responses table...")
                session.execute(text("""
                    CREATE TABLE IF NOT EXISTS cached_responses (
                        id SERIAL PRIMARY KEY,
                        query_hash VARCHAR(64) UNIQUE NOT NULL,
                        query_text TEXT NOT NULL,
                        response TEXT NOT NULL,
                        sources_json TEXT,
                        model_used VARCHAR(64),
                        embedding_compressed TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        expires_at TIMESTAMP WITH TIME ZONE,
                        hit_count INTEGER DEFAULT 0,
                        last_hit_at TIMESTAMP WITH TIME ZONE
                    )
                """))
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_cached_responses_expires 
                    ON cached_responses(expires_at)
                """))
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_cached_responses_hash 
                    ON cached_responses(query_hash)
                """))
                session.commit()
                print("[CACHE] Table created successfully")
                return
            
            # Load non-expired entries (most recent first, limited)
            rows = session.execute(text("""
                SELECT query_hash, query_text, response, sources_json, model_used, 
                       embedding_compressed, created_at, expires_at, hit_count
                FROM cached_responses 
                WHERE expires_at > NOW()
                ORDER BY hit_count DESC, created_at DESC
                LIMIT :limit
            """), {"limit": MAX_MEMORY_CACHE_ENTRIES}).mappings().all()
            
            for row in rows:
                created_ts = row['created_at'].timestamp() if row['created_at'] else time.time()
                expires_ts = row['expires_at'].timestamp() if row['expires_at'] else (time.time() + CACHE_TTL_SECONDS)
                ttl = expires_ts - created_ts
                
                sources = []
                if row['sources_json']:
                    try:
                        sources = json.loads(row['sources_json'])
                    except:
                        pass
                
                embedding = None
                if row['embedding_compressed']:
                    embedding = decompress_embedding(row['embedding_compressed'])
                
                entry = CacheEntry(
                    query=row['query_text'],
                    response=row['response'],
                    sources=sources,
                    model_used=row['model_used'] or "unknown",
                    created_at=created_ts,
                    ttl=ttl,
                    hit_count=row['hit_count'] or 0,
                    embedding=embedding
                )
                
                self.memory_cache[row['query_hash']] = entry
                
                if embedding:
                    self.semantic_entries.append(entry)
            
            print(f"[CACHE] Warmed {len(self.memory_cache)} entries from PostgreSQL")
            
            # Clean up expired entries in background
            session.execute(text("""
                DELETE FROM cached_responses WHERE expires_at < NOW()
            """))
            session.commit()
            
        except Exception as e:
            print(f"[CACHE] Database warm error: {e}")
            session.rollback()
        finally:
            session.close()
    
    def _write_to_database(
        self, 
        key: str, 
        query: str, 
        response: str, 
        sources: List[Dict], 
        model_used: str,
        embedding: Optional[List[float]],
        ttl: float
    ) -> None:
        """Write cache entry to PostgreSQL (async-safe)."""
        if not DB_AVAILABLE:
            return
            
        session = self._get_db_session()
        if not session:
            return
            
        try:
            from sqlalchemy import text
            
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
            sources_json = json.dumps(sources) if sources else None
            embedding_compressed = compress_embedding(embedding) if embedding else None
            
            # Upsert (insert or update)
            session.execute(text("""
                INSERT INTO cached_responses 
                    (query_hash, query_text, response, sources_json, model_used, 
                     embedding_compressed, expires_at, hit_count)
                VALUES 
                    (:hash, :query, :response, :sources, :model, :embedding, :expires, 0)
                ON CONFLICT (query_hash) DO UPDATE SET
                    response = EXCLUDED.response,
                    sources_json = EXCLUDED.sources_json,
                    model_used = EXCLUDED.model_used,
                    embedding_compressed = EXCLUDED.embedding_compressed,
                    expires_at = EXCLUDED.expires_at,
                    created_at = NOW()
            """), {
                "hash": key,
                "query": query,
                "response": response,
                "sources": sources_json,
                "model": model_used,
                "embedding": embedding_compressed,
                "expires": expires_at
            })
            session.commit()
            self.metrics.db_writes += 1
            
        except Exception as e:
            print(f"[CACHE] Database write error: {e}")
            self.metrics.db_errors += 1
            session.rollback()
        finally:
            session.close()
    
    def _check_topic_graph(self, query: str) -> Optional[Tuple[str, List[Dict[str, Any]], str]]:
        """
        Check topic graph for similar cached answers (L3 lookup).
        
        Uses the enhanced question-topic-entity graph for smart cache lookups.
        Prioritizes entity matches (DC codes, forms) for higher precision,
        then falls back to topic matches.
        
        Returns (response, sources, model_used) or None.
        """
        if not DB_AVAILABLE:
            return None
        
        try:
            from src.topic_graph import get_topic_graph
            
            graph = get_topic_graph()
            
            # Classify into topics
            topic_ids = graph.classify_question(query)
            
            # Extract entities (DC codes, forms, conditions)
            entities = graph.extract_entities(query)
            
            # Need at least one signal to proceed
            if not topic_ids and not entities:
                return None
            
            # Enhanced multi-join lookup: entities first (most specific), then topics
            results = graph.find_similar_enhanced(
                topic_ids=topic_ids,
                entities=entities,
                limit=1,
                prefer_verified=True
            )
            
            if results:
                best = results[0]
                match_type = best.get('match_type', 'topic')
                entity_info = f", entities: {[e.value for e in entities]}" if entities else ""
                print(f"[CACHE] L3 {match_type} hit: {query[:40]}... (topics: {topic_ids}{entity_info})")
                return (best['response'], best['sources'], best['model_used'])
            
            return None
            
        except Exception as e:
            print(f"[CACHE] Topic graph lookup error: {e}")
            return None
    
    def _check_database(self, key: str) -> Optional[CacheEntry]:
        """Check PostgreSQL for a cache entry (L2 lookup)."""
        if not DB_AVAILABLE:
            return None
            
        session = self._get_db_session()
        if not session:
            return None
            
        try:
            from sqlalchemy import text
            
            row = session.execute(text("""
                UPDATE cached_responses 
                SET hit_count = hit_count + 1, last_hit_at = NOW()
                WHERE query_hash = :hash AND expires_at > NOW()
                RETURNING query_text, response, sources_json, model_used, 
                          embedding_compressed, created_at, expires_at, hit_count
            """), {"hash": key}).mappings().first()
            
            if row:
                session.commit()
                
                created_ts = row['created_at'].timestamp() if row['created_at'] else time.time()
                expires_ts = row['expires_at'].timestamp() if row['expires_at'] else (time.time() + CACHE_TTL_SECONDS)
                
                sources = []
                if row['sources_json']:
                    try:
                        sources = json.loads(row['sources_json'])
                    except:
                        pass
                
                embedding = None
                if row['embedding_compressed']:
                    embedding = decompress_embedding(row['embedding_compressed'])
                
                entry = CacheEntry(
                    query=row['query_text'],
                    response=row['response'],
                    sources=sources,
                    model_used=row['model_used'] or "unknown",
                    created_at=created_ts,
                    ttl=expires_ts - created_ts,
                    hit_count=row['hit_count'] or 0,
                    embedding=embedding
                )
                
                self.metrics.db_hits += 1
                return entry
            
            session.rollback()  # No update happened
            return None
            
        except Exception as e:
            print(f"[CACHE] Database read error: {e}")
            self.metrics.db_errors += 1
            session.rollback()
            return None
        finally:
            session.close()
    
    def get(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None
    ) -> Optional[Tuple[str, List[Dict[str, Any]], str, str, Optional[float]]]:
        """
        Get a cached response.
        
        Args:
            query: The user query
            query_embedding: Optional query embedding for semantic matching
            
        Returns:
            Tuple of (response, sources, model_used, cache_type, semantic_similarity) or None
            semantic_similarity is only set for semantic cache hits
        """
        key = query_hash(query)
        
        with self._lock:
            # L1: Check memory cache first (instant)
            if key in self.memory_cache:
                entry = self.memory_cache[key]
                if not entry.is_expired():
                    entry.hit_count += 1
                    self.metrics.exact_hits += 1
                    print(f"[CACHE] L1 exact hit: {query[:50]}...")
                    return (entry.response, entry.sources, entry.model_used, "exact", 1.0)  # Exact = 100%
                else:
                    del self.memory_cache[key]
            
            self.metrics.exact_misses += 1
            
            # Try semantic match in memory
            if query_embedding and self.semantic_entries:
                best_match = None
                best_score = 0.0
                
                for entry in self.semantic_entries:
                    if entry.is_expired() or not entry.embedding:
                        continue
                    
                    score = cosine_similarity(query_embedding, entry.embedding)
                    if score > best_score and score >= SEMANTIC_SIMILARITY_THRESHOLD:
                        best_score = score
                        best_match = entry
                
                if best_match:
                    best_match.hit_count += 1
                    self.metrics.semantic_hits += 1
                    print(f"[CACHE] L1 semantic hit (score={best_score:.3f}): {query[:50]}...")
                    return (best_match.response, best_match.sources, best_match.model_used, "semantic", best_score)
                
                self.metrics.semantic_misses += 1
        
        # L2: Check PostgreSQL (slower but persistent)
        db_entry = self._check_database(key)
        if db_entry:
            # Promote to L1
            with self._lock:
                self.memory_cache[key] = db_entry
                if db_entry.embedding:
                    self.semantic_entries.append(db_entry)
                self._evict_memory_if_needed()
            
            print(f"[CACHE] L2 database hit: {query[:50]}...")
            return (db_entry.response, db_entry.sources, db_entry.model_used, "database", 1.0)  # DB exact = 100%
        
        # L3: Check topic graph (finds answers from similar-topic questions)
        topic_result = self._check_topic_graph(query)
        if topic_result:
            response, sources, model_used = topic_result
            self.metrics.topic_hits += 1
            return (response, sources, model_used, "topic", None)  # Topic doesn't have embedding similarity
        
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
        """
        key = query_hash(query)
        
        entry = CacheEntry(
            query=query,
            response=response,
            sources=sources,
            model_used=model_used,
            created_at=time.time(),
            ttl=ttl,
            embedding=query_embedding
        )
        
        # L1: Write to memory
        with self._lock:
            self.memory_cache[key] = entry
            
            if query_embedding:
                self.semantic_entries.append(entry)
            
            self._evict_memory_if_needed()
        
        # L2: Write to PostgreSQL (in background thread to not block)
        if DB_AVAILABLE:
            thread = threading.Thread(
                target=self._write_to_database,
                args=(key, query, response, sources, model_used, query_embedding, ttl)
            )
            thread.daemon = True
            thread.start()
        
        print(f"[CACHE] Stored: {query[:50]}...")
    
    def _evict_memory_if_needed(self) -> None:
        """Evict old entries from memory cache if too large."""
        # Remove expired entries
        expired_keys = [k for k, v in self.memory_cache.items() if v.is_expired()]
        for k in expired_keys:
            del self.memory_cache[k]
        
        self.semantic_entries = [e for e in self.semantic_entries if not e.is_expired()]
        
        # LRU eviction if still too large
        if len(self.memory_cache) > MAX_MEMORY_CACHE_ENTRIES:
            sorted_entries = sorted(
                self.memory_cache.items(),
                key=lambda x: (x[1].hit_count, x[1].created_at)
            )
            to_remove = len(self.memory_cache) - MAX_MEMORY_CACHE_ENTRIES
            for key, _ in sorted_entries[:to_remove]:
                del self.memory_cache[key]
        
        if len(self.semantic_entries) > MAX_MEMORY_CACHE_ENTRIES:
            self.semantic_entries.sort(key=lambda x: (x.hit_count, x.created_at))
            self.semantic_entries = self.semantic_entries[-MAX_MEMORY_CACHE_ENTRIES:]
    
    def clear(self) -> None:
        """Clear all cache entries (memory and database)."""
        with self._lock:
            self.memory_cache.clear()
            self.semantic_entries.clear()
            self.metrics = CacheMetrics()
        
        if DB_AVAILABLE:
            session = self._get_db_session()
            if session:
                try:
                    from sqlalchemy import text
                    session.execute(text("DELETE FROM cached_responses"))
                    session.commit()
                    print("[CACHE] Cleared PostgreSQL cache")
                except Exception as e:
                    print(f"[CACHE] Database clear error: {e}")
                    session.rollback()
                finally:
                    session.close()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics."""
        db_size = 0
        if DB_AVAILABLE:
            session = self._get_db_session()
            if session:
                try:
                    from sqlalchemy import text
                    result = session.execute(text(
                        "SELECT COUNT(*) FROM cached_responses WHERE expires_at > NOW()"
                    )).scalar()
                    db_size = result or 0
                except:
                    pass
                finally:
                    session.close()
        
        return {
            **self.metrics.to_dict(),
            "memory_cache_size": len(self.memory_cache),
            "semantic_cache_size": len(self.semantic_entries),
            "database_cache_size": db_size,
            "database_available": DB_AVAILABLE,
            "max_memory_entries": MAX_MEMORY_CACHE_ENTRIES,
            "max_db_entries": MAX_DB_CACHE_ENTRIES,
            "ttl_hours": CACHE_TTL_SECONDS / 3600
        }


# Global cache instance
_cache: Optional[ResponseCache] = None
_corpus_hash: Optional[str] = None


def get_response_cache(corpus_hash: Optional[str] = None) -> ResponseCache:
    """
    Get or create the global response cache.
    
    Args:
        corpus_hash: Hash of the current corpus. If provided and different from
                    stored hash, cache will be invalidated.
    """
    global _cache, _corpus_hash
    if _cache is None:
        _cache = ResponseCache()
        _cache.initialize(corpus_hash=corpus_hash)
        _corpus_hash = corpus_hash
    elif corpus_hash and corpus_hash != _corpus_hash:
        # Corpus changed after initial init - clear and reinit
        print(f"[CACHE] Corpus hash changed: {_corpus_hash} -> {corpus_hash}")
        _cache.clear()
        _cache._initialized = False
        _cache.initialize(corpus_hash=corpus_hash)
        _corpus_hash = corpus_hash
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
) -> Optional[Tuple[str, List[Dict[str, Any]], str, str, Optional[float]]]:
    """Convenience function to get a cached response.
    
    Returns:
        Tuple of (response, sources, model_used, cache_type, semantic_similarity) or None
    """
    cache = get_response_cache()
    return cache.get(query, query_embedding)
