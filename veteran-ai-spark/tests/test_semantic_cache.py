"""
Tests for semantic cache functionality.
"""

import pytest
import numpy as np
import tempfile
import os
from unittest.mock import Mock, patch

from app.cache import SemanticCache
from app.schemas import TokenUsage
from app.settings import Settings


@pytest.fixture
def temp_cache():
    """Create a temporary cache for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Override settings for testing
        test_settings = Settings(
            openai_api_key="test-key",
            pinecone_api_key="test-key", 
            pinecone_env="test",
            pinecone_index="test",
            cache_db_path=os.path.join(temp_dir, "test_cache.sqlite"),
            faiss_path=os.path.join(temp_dir, "test_faiss.index")
        )
        
        with patch('app.cache.settings', test_settings):
            cache = SemanticCache()
            yield cache


@pytest.fixture
def sample_token_usage():
    """Sample token usage for testing."""
    return TokenUsage(
        model_big="gpt-4o",
        model_small="gpt-4o-mini",
        tokens_big=1500,
        tokens_small=300,
        total_tokens=1800
    )


def test_cache_initialization(temp_cache):
    """Test cache initialization."""
    assert temp_cache.faiss_index is not None
    assert temp_cache.faiss_index.ntotal == 0  # Empty initially
    
    # Test database tables exist
    import sqlite3
    with sqlite3.connect(temp_cache.db_path) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        assert "query_cache" in tables
        assert "faiss_meta" in tables
        assert "doc_meta" in tables


def test_query_normalization():
    """Test query normalization."""
    from app.utils import normalize_query
    
    # Test cases for normalization
    test_cases = [
        ("What is AI?", "what is ai"),
        ("  How   does   it   work?  ", "how does it work"),
        ("UPPERCASE QUERY", "uppercase query"),
        ("Query with punctuation!!!", "query with punctuation"),
        ("Query with numbers 123", "query with numbers 123")
    ]
    
    for input_query, expected in test_cases:
        assert normalize_query(input_query) == expected


@patch('app.cache.SentenceTransformer')
def test_embedding_generation(mock_transformer, temp_cache):
    """Test query embedding generation."""
    # Mock the sentence transformer
    mock_model = Mock()
    mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3] + [0.0] * 381])  # 384 dimensions
    mock_transformer.return_value = mock_model
    
    temp_cache._load_embedding_model()
    
    embedding = temp_cache.embed_query_for_cache("test query")
    
    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (384,)
    assert embedding.dtype == np.float32


def test_exact_cache_hit(temp_cache, sample_token_usage):
    """Test exact cache hit functionality."""
    from app.utils import normalize_query, hash_string
    
    # Create test data
    query = "What is machine learning?"
    normalized = normalize_query(query)
    q_hash = hash_string(normalized)
    embedding = np.random.rand(384).astype(np.float32)
    
    # Record answer
    cache_id = temp_cache.record_answer(
        normalized_query=normalized,
        q_hash=q_hash,
        embedding=embedding,
        answer="Machine learning is a subset of AI.",
        citations=[{"n": 1, "url": "http://example.com"}],
        compressed_pack={"quotes": [], "sources": [], "top_doc_ids": []},
        top_doc_ids=["doc1", "doc2"],
        token_usage=sample_token_usage,
        doc_version_hash="test_hash"
    )
    
    assert cache_id > 0
    
    # Test exact retrieval
    cached_entry = temp_cache.get_exact(q_hash)
    assert cached_entry is not None
    assert cached_entry.answer == "Machine learning is a subset of AI."
    assert cached_entry.q_hash == q_hash


def test_semantic_cache_hit(temp_cache, sample_token_usage):
    """Test semantic cache hit functionality."""
    from app.utils import normalize_query, hash_string
    
    # Record original query
    original_query = "What is artificial intelligence?"
    normalized = normalize_query(original_query)
    q_hash = hash_string(normalized)
    embedding = np.random.rand(384).astype(np.float32)
    
    cache_id = temp_cache.record_answer(
        normalized_query=normalized,
        q_hash=q_hash,
        embedding=embedding,
        answer="AI is the simulation of human intelligence.",
        citations=[],
        compressed_pack={"quotes": [], "sources": [], "top_doc_ids": []},
        top_doc_ids=["doc1"],
        token_usage=sample_token_usage,
        doc_version_hash="test_hash"
    )
    
    # Test semantic search with similar embedding
    similar_embedding = embedding + np.random.normal(0, 0.1, 384).astype(np.float32)
    hits = temp_cache.get_semantic_hits(similar_embedding, top_n=5)
    
    assert len(hits) > 0
    assert hits[0][0] == cache_id  # Should find the cached entry


def test_paraphrase_semantic_hit(temp_cache, sample_token_usage):
    """Test that paraphrases trigger semantic hits."""
    from app.utils import normalize_query, hash_string
    
    # Seed cache with original question
    original = "How does machine learning work?"
    normalized = normalize_query(original)
    q_hash = hash_string(normalized)
    
    # Use a fixed embedding for reproducibility
    embedding = np.ones(384, dtype=np.float32) * 0.5
    
    temp_cache.record_answer(
        normalized_query=normalized,
        q_hash=q_hash,
        embedding=embedding,
        answer="Machine learning works by training algorithms on data.",
        citations=[],
        compressed_pack={"quotes": [], "sources": [], "top_doc_ids": []},
        top_doc_ids=["doc1"],
        token_usage=sample_token_usage,
        doc_version_hash="test_hash"
    )
    
    # Test paraphrase
    paraphrase = "What is the process of machine learning?"
    paraphrase_normalized = normalize_query(paraphrase)
    paraphrase_hash = hash_string(paraphrase_normalized)
    
    # Should not get exact hit
    exact_hit = temp_cache.get_exact(paraphrase_hash)
    assert exact_hit is None
    
    # Should get semantic hit with similar embedding
    similar_embedding = embedding + np.random.normal(0, 0.05, 384).astype(np.float32)
    semantic_hits = temp_cache.get_semantic_hits(similar_embedding, top_n=5)
    
    # Should find at least one hit (the original)
    assert len(semantic_hits) > 0


def test_cache_statistics(temp_cache, sample_token_usage):
    """Test cache statistics functionality."""
    from app.utils import normalize_query, hash_string
    
    # Initially empty
    stats = temp_cache.get_stats()
    assert stats["total_entries"] == 0
    assert stats["total_hits"] == 0
    
    # Add some entries
    for i in range(3):
        query = f"Test query {i}"
        normalized = normalize_query(query)
        q_hash = hash_string(normalized)
        embedding = np.random.rand(384).astype(np.float32)
        
        temp_cache.record_answer(
            normalized_query=normalized,
            q_hash=q_hash,
            embedding=embedding,
            answer=f"Answer {i}",
            citations=[],
            compressed_pack={"quotes": [], "sources": [], "top_doc_ids": []},
            top_doc_ids=[f"doc{i}"],
            token_usage=sample_token_usage,
            doc_version_hash="test_hash"
        )
    
    # Check updated stats
    stats = temp_cache.get_stats()
    assert stats["total_entries"] == 3
    assert stats["faiss_entries"] == 3


def test_cache_touch(temp_cache, sample_token_usage):
    """Test cache touch functionality for hit tracking."""
    from app.utils import normalize_query, hash_string
    
    # Create cache entry
    query = "Test query for touching"
    normalized = normalize_query(query)
    q_hash = hash_string(normalized)
    embedding = np.random.rand(384).astype(np.float32)
    
    cache_id = temp_cache.record_answer(
        normalized_query=normalized,
        q_hash=q_hash,
        embedding=embedding,
        answer="Test answer",
        citations=[],
        compressed_pack={"quotes": [], "sources": [], "top_doc_ids": []},
        top_doc_ids=["doc1"],
        token_usage=sample_token_usage,
        doc_version_hash="test_hash"
    )
    
    # Get initial hit count
    entry = temp_cache.get_cache_entry_by_id(cache_id)
    initial_hits = entry.hits
    
    # Touch the cache entry
    temp_cache.touch(cache_id)
    
    # Check hit count increased
    entry_after = temp_cache.get_cache_entry_by_id(cache_id)
    assert entry_after.hits == initial_hits + 1


def test_cache_clear(temp_cache, sample_token_usage):
    """Test cache clearing functionality."""
    from app.utils import normalize_query, hash_string
    
    # Add entries
    for i in range(2):
        query = f"Query to clear {i}"
        normalized = normalize_query(query)
        q_hash = hash_string(normalized)
        embedding = np.random.rand(384).astype(np.float32)
        
        temp_cache.record_answer(
            normalized_query=normalized,
            q_hash=q_hash,
            embedding=embedding,
            answer=f"Answer {i}",
            citations=[],
            compressed_pack={"quotes": [], "sources": [], "top_doc_ids": []},
            top_doc_ids=[f"doc{i}"],
            token_usage=sample_token_usage,
            doc_version_hash="test_hash"
        )
    
    # Verify entries exist
    stats_before = temp_cache.get_stats()
    assert stats_before["total_entries"] == 2
    
    # Clear cache
    cleared_count = temp_cache.clear_cache()
    assert cleared_count == 2
    
    # Verify cache is empty
    stats_after = temp_cache.get_stats()
    assert stats_after["total_entries"] == 0
    assert stats_after["faiss_entries"] == 0


if __name__ == "__main__":
    pytest.main([__file__])



