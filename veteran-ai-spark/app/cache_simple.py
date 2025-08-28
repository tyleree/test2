"""
Simplified cache implementation without heavy dependencies for testing.
"""

import json
import sqlite3
import threading
import numpy as np
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from .config import config
from .utils import normalize_query, hash_string, stable_hash_list
from .schemas import CacheEntry, TokenUsage


class SimpleSemanticCache:
    """Simplified semantic cache for testing without PyTorch dependencies."""
    
    def __init__(self):
        self.db_path = config.cache_db_path
        self.lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database with WAL mode."""
        with sqlite3.connect(self.db_path) as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")
            
            # Create tables
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized TEXT NOT NULL,
                    q_hash TEXT UNIQUE NOT NULL,
                    emb BLOB,
                    answer TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    compressed_pack_json TEXT NOT NULL,
                    top_doc_ids_json TEXT NOT NULL,
                    token_cost_json TEXT NOT NULL,
                    model_big TEXT NOT NULL,
                    model_small TEXT NOT NULL,
                    doc_version_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_hit_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    hits INTEGER DEFAULT 0
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS doc_meta (
                    doc_id TEXT PRIMARY KEY,
                    source_url TEXT,
                    version_hash TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_q_hash ON query_cache (q_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_version ON query_cache (doc_version_hash)")
            
            conn.commit()
    
    def embed_query_for_cache(self, q: str) -> np.ndarray:
        """Generate simple embedding for query caching (placeholder)."""
        # Simple hash-based embedding for testing
        import hashlib
        hash_obj = hashlib.md5(q.encode())
        # Convert hash to pseudo-embedding (384 dimensions)
        embedding = np.array([float(int(hash_obj.hexdigest()[i:i+2], 16)) for i in range(0, 32, 2)] * 24)
        return embedding.astype(np.float32)
    
    def _serialize_embedding(self, embedding: np.ndarray) -> bytes:
        """Serialize numpy array to bytes for SQLite storage."""
        return embedding.tobytes()
    
    def _deserialize_embedding(self, blob: bytes) -> np.ndarray:
        """Deserialize bytes back to numpy array."""
        return np.frombuffer(blob, dtype=np.float32)
    
    def get_exact(self, q_hash: str) -> Optional[CacheEntry]:
        """Get exact cache hit by query hash."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM query_cache WHERE q_hash = ?", (q_hash,)
            )
            row = cursor.fetchone()
            
            if row:
                return CacheEntry(**dict(row))
            return None
    
    def get_semantic_hits(self, vector: np.ndarray, top_n: int = 10) -> List[Tuple[int, float]]:
        """Get semantic cache hits (simplified - just return recent entries)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id FROM query_cache ORDER BY last_hit_at DESC LIMIT ?", (top_n,)
            )
            rows = cursor.fetchall()
            
            # Return with dummy similarity scores
            return [(row[0], 0.95 - i*0.05) for i, row in enumerate(rows)]
    
    def record_answer(
        self,
        normalized_query: str,
        q_hash: str,
        embedding: np.ndarray,
        answer: str,
        citations: List[Dict],
        compressed_pack: Dict,
        top_doc_ids: List[str],
        token_usage: TokenUsage,
        doc_version_hash: str
    ) -> int:
        """Record new answer in cache atomically."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    INSERT INTO query_cache (
                        normalized, q_hash, emb, answer, citations_json,
                        compressed_pack_json, top_doc_ids_json, token_cost_json,
                        model_big, model_small, doc_version_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    normalized_query,
                    q_hash,
                    self._serialize_embedding(embedding),
                    answer,
                    json.dumps(citations),
                    json.dumps(compressed_pack),
                    json.dumps(top_doc_ids),
                    json.dumps(token_usage.dict()),
                    token_usage.model_big,
                    token_usage.model_small,
                    doc_version_hash
                ))
                
                cache_id = cursor.lastrowid
                conn.commit()
                
                return cache_id
    
    def touch(self, cache_id: int):
        """Update hit counter and last_hit_at for cache entry."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE query_cache 
                SET hits = hits + 1, last_hit_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (cache_id,))
            conn.commit()
    
    def get_cache_entry_by_id(self, cache_id: int) -> Optional[CacheEntry]:
        """Get cache entry by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM query_cache WHERE id = ?", (cache_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return CacheEntry(**dict(row))
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with sqlite3.connect(self.db_path) as conn:
            # Total entries
            total = conn.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0]
            
            # Hit statistics
            hits_data = conn.execute("""
                SELECT SUM(hits) as total_hits, 
                       SUM(CASE WHEN hits = 0 THEN 1 ELSE 0 END) as never_hit
                FROM query_cache
            """).fetchone()
            
            total_hits = hits_data[0] or 0
            never_hit = hits_data[1] or 0
            
            # Calculate hit rate (rough approximation)
            hit_rate = (total_hits / max(total_hits + never_hit, 1)) * 100
            
            return {
                "total_entries": total,
                "total_hits": total_hits,
                "never_hit": never_hit,
                "hit_rate": hit_rate,
                "memory_usage_mb": 0.1,  # Placeholder
                "faiss_entries": total  # Same as total for simple version
            }
    
    def clear_cache(self) -> int:
        """Clear all cache entries. Returns number of entries removed."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                # Count entries before deletion
                count = conn.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0]
                
                # Clear tables
                conn.execute("DELETE FROM query_cache")
                conn.execute("DELETE FROM doc_meta")
                conn.commit()
                
                return count


# Global cache instance
cache = SimpleSemanticCache()







