"""
Timeline tracking system for comprehensive question logging.
Tracks every question, cache hits, token usage, and performance metrics.
"""

import sqlite3
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from contextlib import contextmanager

from .settings import settings

logger = logging.getLogger(__name__)


@dataclass
class TimelineEntry:
    """Single timeline entry for a question."""
    id: Optional[int] = None
    timestamp: Optional[str] = None
    question: str = ""
    question_hash: str = ""
    cache_mode: str = "miss"  # miss, exact_hit, semantic_hit
    semantic_similarity: Optional[float] = None
    answer_preview: str = ""  # First 200 chars
    citations_count: int = 0
    token_usage: Dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    retrieved_docs: int = 0
    compressed_tokens: int = 0
    final_tokens: int = 0
    user_ip: str = ""
    error_message: str = ""
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


class TimelineTracker:
    """Tracks all questions and responses in a comprehensive timeline."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.cache_db_path.replace('cache.sqlite', 'timeline.sqlite')
        self.init_db()
    
    def init_db(self):
        """Initialize timeline database with comprehensive schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS timeline_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    question TEXT NOT NULL,
                    question_hash TEXT NOT NULL,
                    cache_mode TEXT NOT NULL,
                    semantic_similarity REAL,
                    answer_preview TEXT,
                    citations_count INTEGER DEFAULT 0,
                    token_usage TEXT,  -- JSON string
                    latency_ms INTEGER DEFAULT 0,
                    retrieved_docs INTEGER DEFAULT 0,
                    compressed_tokens INTEGER DEFAULT 0,
                    final_tokens INTEGER DEFAULT 0,
                    user_ip TEXT DEFAULT '',
                    error_message TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON timeline_entries(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_mode ON timeline_entries(cache_mode)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_question_hash ON timeline_entries(question_hash)")
            
            conn.commit()
            logger.info("Timeline database initialized")
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()
    
    def log_question(self, entry: TimelineEntry) -> int:
        """Log a question and response to the timeline."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    INSERT INTO timeline_entries (
                        timestamp, question, question_hash, cache_mode, 
                        semantic_similarity, answer_preview, citations_count,
                        token_usage, latency_ms, retrieved_docs, 
                        compressed_tokens, final_tokens, user_ip, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry.timestamp,
                    entry.question,
                    entry.question_hash,
                    entry.cache_mode,
                    entry.semantic_similarity,
                    entry.answer_preview,
                    entry.citations_count,
                    json.dumps(entry.token_usage),
                    entry.latency_ms,
                    entry.retrieved_docs,
                    entry.compressed_tokens,
                    entry.final_tokens,
                    entry.user_ip,
                    entry.error_message
                ))
                
                entry_id = cursor.lastrowid
                conn.commit()
                
                logger.info(f"Logged timeline entry {entry_id}: {entry.cache_mode} - {entry.question[:50]}...")
                return entry_id
                
        except Exception as e:
            logger.error(f"Failed to log timeline entry: {e}")
            return -1
    
    def get_timeline(
        self, 
        limit: int = 100, 
        offset: int = 0,
        cache_mode_filter: str = None,
        date_from: str = None,
        date_to: str = None
    ) -> List[Dict[str, Any]]:
        """Get timeline entries with optional filtering."""
        try:
            query = """
                SELECT 
                    id, timestamp, question, question_hash, cache_mode,
                    semantic_similarity, answer_preview, citations_count,
                    token_usage, latency_ms, retrieved_docs,
                    compressed_tokens, final_tokens, user_ip, error_message,
                    created_at
                FROM timeline_entries 
                WHERE 1=1
            """
            params = []
            
            if cache_mode_filter:
                query += " AND cache_mode = ?"
                params.append(cache_mode_filter)
            
            if date_from:
                query += " AND timestamp >= ?"
                params.append(date_from)
                
            if date_to:
                query += " AND timestamp <= ?"
                params.append(date_to)
            
            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                entries = []
                
                for row in cursor.fetchall():
                    entry = {
                        'id': row[0],
                        'timestamp': row[1],
                        'question': row[2],
                        'question_hash': row[3],
                        'cache_mode': row[4],
                        'semantic_similarity': row[5],
                        'answer_preview': row[6],
                        'citations_count': row[7],
                        'token_usage': json.loads(row[8]) if row[8] else {},
                        'latency_ms': row[9],
                        'retrieved_docs': row[10],
                        'compressed_tokens': row[11],
                        'final_tokens': row[12],
                        'user_ip': row[13],
                        'error_message': row[14],
                        'created_at': row[15]
                    }
                    entries.append(entry)
                
                return entries
                
        except Exception as e:
            logger.error(f"Failed to get timeline: {e}")
            return []
    
    def get_timeline_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get timeline statistics for the last N hours."""
        try:
            cutoff = datetime.utcnow().replace(microsecond=0)
            cutoff = (cutoff - timedelta(hours=hours)).isoformat()
            
            with self._get_connection() as conn:
                # Basic stats
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_questions,
                        SUM(CASE WHEN cache_mode = 'exact_hit' THEN 1 ELSE 0 END) as exact_hits,
                        SUM(CASE WHEN cache_mode = 'semantic_hit' THEN 1 ELSE 0 END) as semantic_hits,
                        SUM(CASE WHEN cache_mode = 'miss' THEN 1 ELSE 0 END) as cache_misses,
                        AVG(latency_ms) as avg_latency,
                        SUM(final_tokens) as total_tokens_used,
                        AVG(semantic_similarity) as avg_similarity
                    FROM timeline_entries 
                    WHERE timestamp >= ?
                """, (cutoff,))
                
                stats = dict(zip([
                    'total_questions', 'exact_hits', 'semantic_hits', 'cache_misses',
                    'avg_latency', 'total_tokens_used', 'avg_similarity'
                ], cursor.fetchone()))
                
                # Cache hit rate
                total = stats['total_questions'] or 1
                cache_hits = (stats['exact_hits'] or 0) + (stats['semantic_hits'] or 0)
                stats['cache_hit_rate'] = (cache_hits / total) * 100
                
                # Hourly breakdown
                cursor = conn.execute("""
                    SELECT 
                        strftime('%H', timestamp) as hour,
                        COUNT(*) as questions,
                        SUM(CASE WHEN cache_mode != 'miss' THEN 1 ELSE 0 END) as hits
                    FROM timeline_entries 
                    WHERE timestamp >= ?
                    GROUP BY strftime('%H', timestamp)
                    ORDER BY hour
                """, (cutoff,))
                
                stats['hourly_breakdown'] = [
                    {'hour': row[0], 'questions': row[1], 'hits': row[2]}
                    for row in cursor.fetchall()
                ]
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get timeline stats: {e}")
            return {}
    
    def get_question_details(self, question_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information for a specific question."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM timeline_entries WHERE id = ?
                """, (question_id,))
                
                row = cursor.fetchone()
                if row:
                    columns = [desc[0] for desc in cursor.description]
                    entry = dict(zip(columns, row))
                    entry['token_usage'] = json.loads(entry['token_usage']) if entry['token_usage'] else {}
                    return entry
                
        except Exception as e:
            logger.error(f"Failed to get question details: {e}")
        
        return None


# Global timeline tracker instance
timeline = TimelineTracker()
