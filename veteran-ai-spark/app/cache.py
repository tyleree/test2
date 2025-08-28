"""
Multi-layer semantic cache implementation using SQLite + FAISS.
"""

import json
import sqlite3
import threading
import numpy as np
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import faiss
from sentence_transformers import SentenceTransformer

from .config import config
from .utils import normalize_query, hash_string, stable_hash_list
from .schemas import CacheEntry, TokenUsage


class SemanticCache:
    """Multi-layer semantic cache with SQLite backend and FAISS index."""
    
    def __init__(self):
        self.db_path = config.cache_db_path
        self.faiss_path = config.faiss_path
        self.embedding_model = None
        self.faiss_index = None
        self.lock = threading.Lock()
        self._init_db()
        self._init_faiss()
        self._load_embedding_model()
    
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
                    emb BLOB NOT NULL,
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
                CREATE TABLE IF NOT EXISTS faiss_meta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_id INTEGER UNIQUE NOT NULL,
                    FOREIGN KEY (cache_id) REFERENCES query_cache (id)
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_id ON faiss_meta (cache_id)")
            
            conn.commit()
    
    def _init_faiss(self):
        """Initialize or load FAISS index."""
        try:
            # Try to load existing index
            self.faiss_index = faiss.read_index(self.faiss_path)
        except:
            # Create new index (384 dimensions for all-MiniLM-L6-v2)
            self.faiss_index = faiss.IndexFlatIP(384)  # Inner product for cosine similarity
            self._save_faiss_index()
    
    def _save_faiss_index(self):
        """Save FAISS index to disk."""
        faiss.write_index(self.faiss_index, self.faiss_path)
    
    def _load_embedding_model(self):
        """Load sentence transformer model for embeddings."""
        if self.embedding_model is None:
            self.embedding_model = SentenceTransformer(getattr(config, "cache_embedding_model", "all-MiniLM-L6-v2"))
    
    def embed_query_for_cache(self, q: str) -> np.ndarray:
        """Generate embedding for query caching."""
        self._load_embedding_model()
        embedding = self.embedding_model.encode([q], normalize_embeddings=True)
        return embedding[0].astype(np.float32)
    
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
        """Get semantic cache hits using FAISS search."""
        if self.faiss_index.ntotal == 0:
            return []
        
        # Search FAISS index
        vector = vector.reshape(1, -1).astype(np.float32)
        scores, indices = self.faiss_index.search(vector, min(top_n, self.faiss_index.ntotal))
        
        # Convert to list of (cache_id, similarity_score)
        results = []
        with sqlite3.connect(self.db_path) as conn:
            for i, (faiss_idx, score) in enumerate(zip(indices[0], scores[0])):
                if faiss_idx == -1:  # FAISS returns -1 for empty slots
                    continue
                
                # Get cache_id from faiss_meta
                cursor = conn.execute(
                    "SELECT cache_id FROM faiss_meta WHERE id = ?", (int(faiss_idx) + 1,)
                )
                row = cursor.fetchone()
                if row:
                    results.append((row[0], float(score)))
        
        return results
    
    def faiss_add(self, cache_id: int, vector: np.ndarray):
        """Add vector to FAISS index and update metadata."""
        with self.lock:
            # Add to FAISS
            vector = vector.reshape(1, -1).astype(np.float32)
            self.faiss_index.add(vector)
            
            # Add metadata mapping
            faiss_idx = self.faiss_index.ntotal  # Current size after adding
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO faiss_meta (cache_id) VALUES (?)", (cache_id,)
                )
                conn.commit()
            
            # Save updated index
            self._save_faiss_index()
    
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
                
                # Add to FAISS index
                self.faiss_add(cache_id, embedding)
                
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
            
            # Memory usage (rough estimate)
            memory_mb = (self.faiss_index.ntotal * 384 * 4) / (1024 * 1024)  # 4 bytes per float32
            
            return {
                "total_entries": total,
                "total_hits": total_hits,
                "never_hit": never_hit,
                "hit_rate": hit_rate,
                "memory_usage_mb": memory_mb,
                "faiss_entries": self.faiss_index.ntotal
            }
    
    def clear_cache(self) -> int:
        """Clear all cache entries. Returns number of entries removed."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                # Count entries before deletion
                count = conn.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0]
                
                # Clear tables
                conn.execute("DELETE FROM faiss_meta")
                conn.execute("DELETE FROM query_cache")
                conn.execute("DELETE FROM doc_meta")
                conn.commit()
            
            # Recreate FAISS index
            self.faiss_index = faiss.IndexFlatIP(384)
            self._save_faiss_index()
            
            return count
    
    def update_doc_meta(self, doc_id: str, source_url: str, version_hash: str):
        """Update document metadata."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO doc_meta (doc_id, source_url, version_hash, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (doc_id, source_url, version_hash))
            conn.commit()
    
    def get_doc_version_hash(self, doc_id: str) -> Optional[str]:
        """Get document version hash."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT version_hash FROM doc_meta WHERE doc_id = ?", (doc_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else None


# Global cache instance
cache = SemanticCache()
