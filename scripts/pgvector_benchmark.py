#!/usr/bin/env python3
"""
pgvector Benchmark Harness for Veterans Benefits AI

This script benchmarks PostgreSQL + pgvector performance with HNSW indexing.
It measures latency, throughput, and resource usage across different configurations.

Usage:
    python scripts/pgvector_benchmark.py [--setup] [--benchmark] [--plot]

Requirements:
    - PostgreSQL with pgvector extension
    - DATABASE_URL environment variable set
    - Python packages: psycopg2, numpy, matplotlib
"""

import os
import sys
import json
import time
import random
import argparse
import statistics
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple
import threading

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psycopg2
    from psycopg2.extras import execute_values
    import numpy as np
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install psycopg2-binary numpy")
    sys.exit(1)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class BenchmarkConfig:
    """Benchmark configuration parameters."""
    embedding_dim: int = 1536
    
    # Query workloads
    single_query_count: int = 100      # Number of single queries for latency test
    batch_query_count: int = 500       # Number of sequential batch queries
    concurrent_threads: int = 4        # Number of concurrent threads
    concurrent_queries_per_thread: int = 50  # Queries per thread in concurrent test
    
    # HNSW index parameters
    hnsw_m: int = 16                    # Max connections per layer
    hnsw_ef_construction: int = 64     # Size of dynamic candidate list for construction
    hnsw_ef_search: int = 40           # Size of dynamic candidate list for search
    
    # Top-K for similarity search
    top_k: int = 7
    
    # Paths
    embeddings_cache_path: str = "data/embeddings_cache.json"
    corpus_path: str = "veteran-ai-spark/corpus/vbkb_restructured.json"
    results_dir: str = "benchmark_results"


@dataclass
class LatencyStats:
    """Latency statistics for a benchmark run."""
    count: int = 0
    mean_ms: float = 0.0
    median_ms: float = 0.0
    std_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    
    @classmethod
    def from_latencies(cls, latencies_ms: List[float]) -> 'LatencyStats':
        if not latencies_ms:
            return cls()
        
        sorted_lat = sorted(latencies_ms)
        n = len(sorted_lat)
        
        return cls(
            count=n,
            mean_ms=statistics.mean(sorted_lat),
            median_ms=statistics.median(sorted_lat),
            std_ms=statistics.stdev(sorted_lat) if n > 1 else 0.0,
            min_ms=sorted_lat[0],
            max_ms=sorted_lat[-1],
            p95_ms=sorted_lat[int(n * 0.95)] if n > 1 else sorted_lat[0],
            p99_ms=sorted_lat[int(n * 0.99)] if n > 1 else sorted_lat[0],
        )


@dataclass
class BenchmarkResult:
    """Results from a single benchmark configuration."""
    config_name: str
    index_type: str                    # "none", "hnsw_m16", "hnsw_m24"
    dataset_size: int
    embedding_dim: int
    
    # Index metrics
    index_build_time_sec: float = 0.0
    
    # Single query latency
    single_query_stats: LatencyStats = field(default_factory=LatencyStats)
    
    # Batch query latency
    batch_query_stats: LatencyStats = field(default_factory=LatencyStats)
    
    # Concurrent query metrics
    concurrent_qps: float = 0.0
    concurrent_latency_stats: LatencyStats = field(default_factory=LatencyStats)
    
    # Metadata
    timestamp: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_name": self.config_name,
            "index_type": self.index_type,
            "dataset_size": self.dataset_size,
            "embedding_dim": self.embedding_dim,
            "index_build_time_sec": self.index_build_time_sec,
            "single_query": asdict(self.single_query_stats),
            "batch_query": asdict(self.batch_query_stats),
            "concurrent_qps": self.concurrent_qps,
            "concurrent_latency": asdict(self.concurrent_latency_stats),
            "timestamp": self.timestamp,
        }


# =============================================================================
# Database Operations
# =============================================================================

class PgVectorBenchmark:
    """PostgreSQL + pgvector benchmark harness."""
    
    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.conn = None
        self.embeddings_data: List[Dict[str, Any]] = []
        self.corpus_data: List[Dict[str, Any]] = []
        
    def connect(self) -> bool:
        """Connect to PostgreSQL database."""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("ERROR: DATABASE_URL environment variable not set")
            return False
        
        try:
            self.conn = psycopg2.connect(database_url)
            self.conn.autocommit = False
            print(f"Connected to PostgreSQL")
            return True
        except Exception as e:
            print(f"ERROR: Failed to connect to database: {e}")
            return False
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def setup_database(self) -> bool:
        """Set up pgvector extension and tables."""
        if not self.conn:
            return False
        
        try:
            cur = self.conn.cursor()
            
            # Enable pgvector extension
            print("Enabling pgvector extension...")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Drop existing table
            print("Creating corpus_embeddings table...")
            cur.execute("DROP TABLE IF EXISTS corpus_embeddings;")
            
            # Create table
            cur.execute(f"""
                CREATE TABLE corpus_embeddings (
                    id SERIAL PRIMARY KEY,
                    chunk_id VARCHAR(128) UNIQUE NOT NULL,
                    embedding vector({self.config.embedding_dim}) NOT NULL,
                    topic VARCHAR(256),
                    subtopic VARCHAR(256),
                    url TEXT,
                    content_preview TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """)
            
            # Create B-tree indexes
            cur.execute("CREATE INDEX idx_corpus_chunk_id ON corpus_embeddings(chunk_id);")
            cur.execute("CREATE INDEX idx_corpus_topic ON corpus_embeddings(topic);")
            
            self.conn.commit()
            print("Database setup complete")
            return True
            
        except Exception as e:
            print(f"ERROR: Database setup failed: {e}")
            self.conn.rollback()
            return False
    
    def load_embeddings(self) -> bool:
        """Load embeddings from cache file or generate them."""
        cache_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.config.embeddings_cache_path
        )
        
        # Try to load from cache first
        if os.path.exists(cache_path):
            print(f"Loading embeddings from {cache_path}...")
            try:
                with open(cache_path, 'r') as f:
                    cache_data = json.load(f)
                
                # Handle different cache formats
                if "embeddings" in cache_data:
                    # Format: {"embeddings": {"id": [vec], ...}}
                    embeddings_dict = cache_data["embeddings"]
                    self.embeddings_data = [
                        {"id": doc_id, "embedding": vec}
                        for doc_id, vec in embeddings_dict.items()
                    ]
                elif isinstance(cache_data, list):
                    # Format: [{"id": ..., "embedding": ...}, ...]
                    self.embeddings_data = cache_data
                elif isinstance(cache_data, dict):
                    # Format: {"id": [vec], ...}
                    self.embeddings_data = [
                        {"id": doc_id, "embedding": vec}
                        for doc_id, vec in cache_data.items()
                        if isinstance(vec, list)
                    ]
                
                print(f"Loaded {len(self.embeddings_data)} embeddings from cache")
                return True
            except Exception as e:
                print(f"WARNING: Failed to load cache: {e}")
        
        # No cache - generate embeddings from corpus
        print("No embedding cache found. Generating embeddings from corpus...")
        
        if not self.corpus_data:
            print("ERROR: Must load corpus first before generating embeddings")
            return False
        
        # Check for OpenAI API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("ERROR: OPENAI_API_KEY environment variable required to generate embeddings")
            return False
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            
            self.embeddings_data = []
            batch_size = 100
            total = len(self.corpus_data)
            
            print(f"Generating embeddings for {total} chunks...")
            
            for i in range(0, total, batch_size):
                batch = self.corpus_data[i:i + batch_size]
                texts = [chunk.get("content", "")[:8000] for chunk in batch]  # Truncate long texts
                ids = [chunk.get("entry_id", f"chunk_{i+j}") for j, chunk in enumerate(batch)]
                
                # Generate embeddings
                response = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts
                )
                
                for j, emb_data in enumerate(response.data):
                    self.embeddings_data.append({
                        "id": ids[j],
                        "embedding": emb_data.embedding
                    })
                
                print(f"  Progress: {min(i + batch_size, total)}/{total}")
                time.sleep(0.5)  # Rate limit
            
            # Save cache for next time
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            embeddings_dict = {e["id"]: e["embedding"] for e in self.embeddings_data}
            with open(cache_path, 'w') as f:
                json.dump({
                    "embeddings": embeddings_dict,
                    "model": "text-embedding-3-small",
                    "created_at": datetime.now().isoformat(),
                    "count": len(embeddings_dict)
                }, f)
            print(f"Saved embeddings cache to {cache_path}")
            
            print(f"Generated {len(self.embeddings_data)} embeddings")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to generate embeddings: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def load_corpus(self) -> bool:
        """Load corpus metadata."""
        corpus_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            self.config.corpus_path
        )
        
        if not os.path.exists(corpus_path):
            print(f"ERROR: Corpus not found at {corpus_path}")
            return False
        
        print(f"Loading corpus from {corpus_path}...")
        
        try:
            with open(corpus_path, 'r') as f:
                self.corpus_data = json.load(f)
            
            print(f"Loaded {len(self.corpus_data)} corpus chunks")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to load corpus: {e}")
            return False
    
    def insert_embeddings(self) -> int:
        """Insert embeddings into PostgreSQL in batches."""
        if not self.conn or not self.embeddings_data:
            return 0
        
        print("Inserting embeddings into PostgreSQL...")
        
        # Build lookup from corpus
        corpus_lookup = {}
        for chunk in self.corpus_data:
            chunk_id = chunk.get("entry_id", "")
            if chunk_id:
                corpus_lookup[chunk_id] = chunk
        
        # Prepare data for insert
        rows = []
        for entry in self.embeddings_data:
            chunk_id = entry.get("id", "")
            embedding = entry.get("embedding", [])
            
            if not chunk_id or not embedding:
                continue
            
            # Get metadata from corpus
            corpus_entry = corpus_lookup.get(chunk_id, {})
            
            rows.append((
                chunk_id,
                embedding,
                corpus_entry.get("topic", ""),
                corpus_entry.get("subtopic", ""),
                corpus_entry.get("url", ""),
                corpus_entry.get("content", "")[:500] if corpus_entry.get("content") else "",
            ))
        
        if not rows:
            print("ERROR: No valid embeddings to insert")
            return 0
        
        # Insert in batches to avoid timeout
        batch_size = 50  # Small batches for remote DB
        total = len(rows)
        inserted = 0
        
        try:
            cur = self.conn.cursor()
            
            insert_sql = """
                INSERT INTO corpus_embeddings 
                (chunk_id, embedding, topic, subtopic, url, content_preview)
                VALUES %s
                ON CONFLICT (chunk_id) DO NOTHING
            """
            
            for i in range(0, total, batch_size):
                batch = rows[i:i + batch_size]
                execute_values(cur, insert_sql, batch, template="(%s, %s, %s, %s, %s, %s)")
                self.conn.commit()
                inserted += len(batch)
                print(f"  Inserted {inserted}/{total} embeddings...")
            
            # Get count
            cur.execute("SELECT COUNT(*) FROM corpus_embeddings;")
            count = cur.fetchone()[0]
            
            print(f"Inserted {count} embeddings total")
            return count
            
        except Exception as e:
            print(f"ERROR: Failed to insert embeddings: {e}")
            import traceback
            traceback.print_exc()
            try:
                self.conn.rollback()
            except:
                pass
            return 0
    
    def create_hnsw_index(self, m: int = 16, ef_construction: int = 64) -> float:
        """Create HNSW index and return build time in seconds."""
        if not self.conn:
            return 0.0
        
        index_name = f"idx_corpus_hnsw_m{m}"
        
        print(f"Creating HNSW index (m={m}, ef_construction={ef_construction})...")
        
        try:
            cur = self.conn.cursor()
            
            # Drop existing HNSW indexes
            cur.execute("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'corpus_embeddings' 
                AND indexname LIKE 'idx_corpus_hnsw%';
            """)
            existing_indexes = cur.fetchall()
            
            for (idx_name,) in existing_indexes:
                print(f"Dropping existing index: {idx_name}")
                cur.execute(f"DROP INDEX IF EXISTS {idx_name};")
            
            self.conn.commit()
            
            # Create new HNSW index with timing
            start_time = time.time()
            
            cur.execute(f"""
                CREATE INDEX {index_name} ON corpus_embeddings 
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = {m}, ef_construction = {ef_construction});
            """)
            
            self.conn.commit()
            
            build_time = time.time() - start_time
            print(f"HNSW index created in {build_time:.2f} seconds")
            
            return build_time
            
        except Exception as e:
            print(f"ERROR: Failed to create HNSW index: {e}")
            self.conn.rollback()
            return 0.0
    
    def drop_hnsw_index(self) -> bool:
        """Drop all HNSW indexes."""
        if not self.conn:
            return False
        
        try:
            cur = self.conn.cursor()
            
            cur.execute("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'corpus_embeddings' 
                AND indexname LIKE 'idx_corpus_hnsw%';
            """)
            existing_indexes = cur.fetchall()
            
            for (idx_name,) in existing_indexes:
                print(f"Dropping index: {idx_name}")
                cur.execute(f"DROP INDEX IF EXISTS {idx_name};")
            
            self.conn.commit()
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to drop HNSW index: {e}")
            self.conn.rollback()
            return False
    
    def get_random_query_embedding(self) -> List[float]:
        """Get a random embedding from the dataset for query testing."""
        if not self.embeddings_data:
            return [random.random() for _ in range(self.config.embedding_dim)]
        
        entry = random.choice(self.embeddings_data)
        return entry.get("embedding", [random.random() for _ in range(self.config.embedding_dim)])
    
    def run_single_query(self, query_embedding: List[float]) -> Tuple[float, int]:
        """
        Run a single similarity query and return (latency_ms, result_count).
        """
        if not self.conn:
            return (0.0, 0)
        
        try:
            cur = self.conn.cursor()
            
            # Format embedding as PostgreSQL array
            embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
            
            start_time = time.time()
            
            cur.execute(f"""
                SELECT chunk_id, 1 - (embedding <=> '{embedding_str}'::vector) AS similarity
                FROM corpus_embeddings
                ORDER BY embedding <=> '{embedding_str}'::vector
                LIMIT {self.config.top_k};
            """)
            
            results = cur.fetchall()
            
            latency_ms = (time.time() - start_time) * 1000
            
            return (latency_ms, len(results))
            
        except Exception as e:
            print(f"Query error: {e}")
            return (0.0, 0)
    
    def benchmark_single_queries(self, count: int) -> LatencyStats:
        """Run single query latency benchmark."""
        print(f"Running {count} single queries...")
        
        latencies = []
        
        for i in range(count):
            query_embedding = self.get_random_query_embedding()
            latency_ms, _ = self.run_single_query(query_embedding)
            latencies.append(latency_ms)
            
            if (i + 1) % 20 == 0:
                print(f"  Completed {i + 1}/{count} queries")
        
        stats = LatencyStats.from_latencies(latencies)
        print(f"  Single query stats: median={stats.median_ms:.2f}ms, p95={stats.p95_ms:.2f}ms")
        
        return stats
    
    def benchmark_batch_queries(self, count: int) -> LatencyStats:
        """Run sequential batch query benchmark."""
        print(f"Running {count} batch queries...")
        
        latencies = []
        
        for i in range(count):
            query_embedding = self.get_random_query_embedding()
            latency_ms, _ = self.run_single_query(query_embedding)
            latencies.append(latency_ms)
            
            if (i + 1) % 100 == 0:
                print(f"  Completed {i + 1}/{count} queries")
        
        stats = LatencyStats.from_latencies(latencies)
        print(f"  Batch query stats: median={stats.median_ms:.2f}ms, p95={stats.p95_ms:.2f}ms")
        
        return stats
    
    def _concurrent_worker(self, thread_id: int, query_count: int, results: List[float]):
        """Worker function for concurrent benchmark."""
        # Create new connection for this thread
        database_url = os.getenv("DATABASE_URL")
        conn = psycopg2.connect(database_url)
        
        try:
            cur = conn.cursor()
            
            for _ in range(query_count):
                query_embedding = self.get_random_query_embedding()
                embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
                
                start_time = time.time()
                
                cur.execute(f"""
                    SELECT chunk_id, 1 - (embedding <=> '{embedding_str}'::vector) AS similarity
                    FROM corpus_embeddings
                    ORDER BY embedding <=> '{embedding_str}'::vector
                    LIMIT {self.config.top_k};
                """)
                
                cur.fetchall()
                
                latency_ms = (time.time() - start_time) * 1000
                results.append(latency_ms)
                
        finally:
            conn.close()
    
    def benchmark_concurrent_queries(self, threads: int, queries_per_thread: int) -> Tuple[float, LatencyStats]:
        """
        Run concurrent query benchmark.
        Returns (QPS, latency_stats).
        """
        print(f"Running concurrent benchmark: {threads} threads, {queries_per_thread} queries each...")
        
        # Thread-safe results collection
        all_latencies = []
        lock = threading.Lock()
        
        def worker(thread_id: int):
            local_latencies = []
            self._concurrent_worker(thread_id, queries_per_thread, local_latencies)
            with lock:
                all_latencies.extend(local_latencies)
        
        start_time = time.time()
        
        # Run concurrent workers
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(worker, i) for i in range(threads)]
            for future in as_completed(futures):
                future.result()  # Raise any exceptions
        
        total_time = time.time() - start_time
        total_queries = threads * queries_per_thread
        qps = total_queries / total_time
        
        stats = LatencyStats.from_latencies(all_latencies)
        
        print(f"  Concurrent stats: QPS={qps:.1f}, median={stats.median_ms:.2f}ms, p95={stats.p95_ms:.2f}ms")
        
        return (qps, stats)
    
    def run_full_benchmark(self, index_type: str = "none", hnsw_m: int = 16, hnsw_ef: int = 64) -> BenchmarkResult:
        """Run complete benchmark for a configuration."""
        
        print(f"\n{'='*60}")
        print(f"Running benchmark: index_type={index_type}")
        print(f"{'='*60}")
        
        # Get dataset size
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM corpus_embeddings;")
        dataset_size = cur.fetchone()[0]
        
        result = BenchmarkResult(
            config_name=f"{index_type}_benchmark",
            index_type=index_type,
            dataset_size=dataset_size,
            embedding_dim=self.config.embedding_dim,
            timestamp=datetime.now().isoformat(),
        )
        
        # Handle index
        if index_type == "none":
            self.drop_hnsw_index()
            result.index_build_time_sec = 0.0
        else:
            m = int(index_type.split("_m")[1]) if "_m" in index_type else hnsw_m
            result.index_build_time_sec = self.create_hnsw_index(m=m, ef_construction=hnsw_ef)
        
        # Warm-up queries
        print("Running warm-up queries...")
        for _ in range(10):
            self.run_single_query(self.get_random_query_embedding())
        
        # Single query benchmark
        result.single_query_stats = self.benchmark_single_queries(self.config.single_query_count)
        
        # Batch query benchmark
        result.batch_query_stats = self.benchmark_batch_queries(self.config.batch_query_count)
        
        # Concurrent benchmark
        qps, concurrent_stats = self.benchmark_concurrent_queries(
            self.config.concurrent_threads,
            self.config.concurrent_queries_per_thread
        )
        result.concurrent_qps = qps
        result.concurrent_latency_stats = concurrent_stats
        
        return result


# =============================================================================
# Results and Plotting
# =============================================================================

def save_results(results: List[BenchmarkResult], output_dir: str):
    """Save benchmark results to JSON and CSV."""
    os.makedirs(output_dir, exist_ok=True)
    
    # JSON output
    json_path = os.path.join(output_dir, "pgvector_metrics.json")
    results_dict = [r.to_dict() for r in results]
    
    with open(json_path, 'w') as f:
        json.dump(results_dict, f, indent=2)
    
    print(f"Saved JSON results to {json_path}")
    
    # CSV output
    csv_path = os.path.join(output_dir, "pgvector_metrics.csv")
    
    with open(csv_path, 'w') as f:
        # Header
        f.write("config_name,index_type,dataset_size,index_build_time_sec,")
        f.write("single_median_ms,single_p95_ms,single_p99_ms,")
        f.write("batch_median_ms,batch_p95_ms,batch_p99_ms,")
        f.write("concurrent_qps,concurrent_median_ms,concurrent_p95_ms\n")
        
        for r in results:
            f.write(f"{r.config_name},{r.index_type},{r.dataset_size},{r.index_build_time_sec:.3f},")
            f.write(f"{r.single_query_stats.median_ms:.3f},{r.single_query_stats.p95_ms:.3f},{r.single_query_stats.p99_ms:.3f},")
            f.write(f"{r.batch_query_stats.median_ms:.3f},{r.batch_query_stats.p95_ms:.3f},{r.batch_query_stats.p99_ms:.3f},")
            f.write(f"{r.concurrent_qps:.1f},{r.concurrent_latency_stats.median_ms:.3f},{r.concurrent_latency_stats.p95_ms:.3f}\n")
    
    print(f"Saved CSV results to {csv_path}")


def generate_plots(results: List[BenchmarkResult], output_dir: str):
    """Generate benchmark visualization plots."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
    except ImportError:
        print("matplotlib not available, skipping plots")
        return
    
    plots_dir = os.path.join(output_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)
    
    # Extract data for plotting
    configs = [r.index_type for r in results]
    
    # 1. Latency Comparison Bar Chart
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(configs))
    width = 0.25
    
    medians = [r.single_query_stats.median_ms for r in results]
    p95s = [r.single_query_stats.p95_ms for r in results]
    p99s = [r.single_query_stats.p99_ms for r in results]
    
    bars1 = ax.bar(x - width, medians, width, label='Median', color='#2ecc71')
    bars2 = ax.bar(x, p95s, width, label='P95', color='#f39c12')
    bars3 = ax.bar(x + width, p99s, width, label='P99', color='#e74c3c')
    
    ax.set_xlabel('Configuration')
    ax.set_ylabel('Latency (ms)')
    ax.set_title('Single Query Latency by Configuration')
    ax.set_xticks(x)
    ax.set_xticklabels(configs)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels
    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.1f}',
                       xy=(bar.get_x() + bar.get_width() / 2, height),
                       xytext=(0, 3), textcoords="offset points",
                       ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'latency_comparison.png'), dpi=150)
    plt.close()
    print(f"Saved latency_comparison.png")
    
    # 2. Throughput (QPS) Comparison
    fig, ax = plt.subplots(figsize=(8, 6))
    
    qps_values = [r.concurrent_qps for r in results]
    colors = ['#3498db' if 'hnsw' in c else '#95a5a6' for c in configs]
    
    bars = ax.bar(configs, qps_values, color=colors)
    
    ax.set_xlabel('Configuration')
    ax.set_ylabel('Queries per Second (QPS)')
    ax.set_title('Concurrent Query Throughput')
    ax.grid(axis='y', alpha=0.3)
    
    for bar, val in zip(bars, qps_values):
        ax.annotate(f'{val:.1f}',
                   xy=(bar.get_x() + bar.get_width() / 2, val),
                   xytext=(0, 3), textcoords="offset points",
                   ha='center', va='bottom', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'throughput_comparison.png'), dpi=150)
    plt.close()
    print(f"Saved throughput_comparison.png")
    
    # 3. Index Build Time
    fig, ax = plt.subplots(figsize=(8, 5))
    
    build_times = [r.index_build_time_sec for r in results]
    colors = ['#9b59b6' if t > 0 else '#bdc3c7' for t in build_times]
    
    bars = ax.bar(configs, build_times, color=colors)
    
    ax.set_xlabel('Configuration')
    ax.set_ylabel('Build Time (seconds)')
    ax.set_title('HNSW Index Build Time')
    ax.grid(axis='y', alpha=0.3)
    
    for bar, val in zip(bars, build_times):
        if val > 0:
            ax.annotate(f'{val:.2f}s',
                       xy=(bar.get_x() + bar.get_width() / 2, val),
                       xytext=(0, 3), textcoords="offset points",
                       ha='center', va='bottom')
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'index_build_time.png'), dpi=150)
    plt.close()
    print(f"Saved index_build_time.png")
    
    # 4. Latency Distribution Box Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # We don't have raw latencies stored, so create a simplified comparison
    data_summary = []
    labels = []
    
    for r in results:
        data_summary.append([
            r.single_query_stats.min_ms,
            r.single_query_stats.median_ms - r.single_query_stats.std_ms,
            r.single_query_stats.median_ms,
            r.single_query_stats.median_ms + r.single_query_stats.std_ms,
            r.single_query_stats.max_ms
        ])
        labels.append(r.index_type)
    
    # Create box plot style visualization
    positions = range(len(results))
    
    for i, (r, pos) in enumerate(zip(results, positions)):
        color = '#2ecc71' if 'hnsw' in r.index_type else '#e74c3c'
        
        # Box (Q1 to Q3 approximation)
        ax.bar(pos, r.single_query_stats.p95_ms - r.single_query_stats.median_ms,
               bottom=r.single_query_stats.median_ms,
               width=0.4, color=color, alpha=0.7)
        ax.bar(pos, r.single_query_stats.median_ms - r.single_query_stats.min_ms,
               bottom=r.single_query_stats.min_ms,
               width=0.4, color=color, alpha=0.4)
        
        # Median line
        ax.hlines(r.single_query_stats.median_ms, pos - 0.2, pos + 0.2, colors='black', linewidth=2)
        
        # Whiskers
        ax.vlines(pos, r.single_query_stats.min_ms, r.single_query_stats.max_ms, colors='black', linewidth=1)
    
    ax.set_xlabel('Configuration')
    ax.set_ylabel('Latency (ms)')
    ax.set_title('Latency Distribution by Configuration')
    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(plots_dir, 'latency_distribution.png'), dpi=150)
    plt.close()
    print(f"Saved latency_distribution.png")
    
    print(f"\nAll plots saved to {plots_dir}/")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="pgvector Benchmark Harness")
    parser.add_argument("--setup", action="store_true", help="Set up database and load embeddings")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmarks")
    parser.add_argument("--plot", action="store_true", help="Generate plots from existing results")
    parser.add_argument("--all", action="store_true", help="Run setup, benchmark, and plot")
    
    args = parser.parse_args()
    
    if not any([args.setup, args.benchmark, args.plot, args.all]):
        args.all = True  # Default to running everything
    
    config = BenchmarkConfig()
    benchmark = PgVectorBenchmark(config)
    
    results_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        config.results_dir
    )
    
    if args.setup or args.all:
        print("\n" + "="*60)
        print("PHASE 1: DATABASE SETUP")
        print("="*60)
        
        if not benchmark.connect():
            return 1
        
        if not benchmark.setup_database():
            benchmark.close()
            return 1
        
        # Load corpus FIRST (needed for embedding generation)
        if not benchmark.load_corpus():
            benchmark.close()
            return 1
        
        # Then load or generate embeddings
        if not benchmark.load_embeddings():
            benchmark.close()
            return 1
        
        count = benchmark.insert_embeddings()
        if count == 0:
            print("ERROR: No embeddings inserted")
            benchmark.close()
            return 1
        
        print(f"\nSetup complete: {count} embeddings loaded")
    
    results = []
    
    if args.benchmark or args.all:
        print("\n" + "="*60)
        print("PHASE 2: RUNNING BENCHMARKS")
        print("="*60)
        
        if not benchmark.conn:
            if not benchmark.connect():
                return 1
        
        # Benchmark 1: No index (sequential scan)
        result_none = benchmark.run_full_benchmark(index_type="none")
        results.append(result_none)
        
        # Benchmark 2: HNSW with m=16
        result_hnsw16 = benchmark.run_full_benchmark(index_type="hnsw_m16", hnsw_m=16, hnsw_ef=64)
        results.append(result_hnsw16)
        
        # Benchmark 3: HNSW with m=24 (higher quality)
        result_hnsw24 = benchmark.run_full_benchmark(index_type="hnsw_m24", hnsw_m=24, hnsw_ef=128)
        results.append(result_hnsw24)
        
        # Save results
        save_results(results, results_dir)
    
    if args.plot or args.all:
        print("\n" + "="*60)
        print("PHASE 3: GENERATING PLOTS")
        print("="*60)
        
        # Load results if not already in memory
        if not results:
            json_path = os.path.join(results_dir, "pgvector_metrics.json")
            if os.path.exists(json_path):
                with open(json_path, 'r') as f:
                    results_data = json.load(f)
                
                # Reconstruct BenchmarkResult objects
                for rd in results_data:
                    r = BenchmarkResult(
                        config_name=rd["config_name"],
                        index_type=rd["index_type"],
                        dataset_size=rd["dataset_size"],
                        embedding_dim=rd["embedding_dim"],
                        index_build_time_sec=rd["index_build_time_sec"],
                        single_query_stats=LatencyStats(**rd["single_query"]),
                        batch_query_stats=LatencyStats(**rd["batch_query"]),
                        concurrent_qps=rd["concurrent_qps"],
                        concurrent_latency_stats=LatencyStats(**rd["concurrent_latency"]),
                        timestamp=rd["timestamp"],
                    )
                    results.append(r)
            else:
                print(f"ERROR: No results found at {json_path}")
                return 1
        
        generate_plots(results, results_dir)
    
    benchmark.close()
    
    print("\n" + "="*60)
    print("BENCHMARK COMPLETE")
    print("="*60)
    
    # Print summary
    if results:
        print("\nSummary:")
        print("-" * 60)
        for r in results:
            print(f"\n{r.index_type}:")
            print(f"  Single Query: median={r.single_query_stats.median_ms:.2f}ms, p95={r.single_query_stats.p95_ms:.2f}ms")
            print(f"  Concurrent:   QPS={r.concurrent_qps:.1f}, median={r.concurrent_latency_stats.median_ms:.2f}ms")
            if r.index_build_time_sec > 0:
                print(f"  Index Build:  {r.index_build_time_sec:.2f}s")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

