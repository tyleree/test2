"""
Tests for semantic caching functionality.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch

from app.cache import SemanticCache, CacheEntry, CacheHit
from app.answer import AnswerResult, Citation

class TestSemanticCache:
    """Test semantic caching system."""
    
    @pytest.fixture
    def cache(self, temp_db, mock_openai):
        """Create test cache instance."""
        return SemanticCache(temp_db)
    
    @pytest.fixture
    def sample_answer_result(self):
        """Sample answer result for testing."""
        return AnswerResult(
            answer_plain="Test answer with citation [1].",
            answer_html="<p>Test answer with citation [1].</p><p><strong>Sources</strong></p><ol><li><a href='https://example.com'>[1] Test Source</a></li></ol>",
            citations=[Citation(n=1, url="https://example.com", title="Test Source")],
            token_usage={'total_tokens': 100},
            status='success'
        )
    
    def test_init(self, temp_db, mock_openai):
        """Test cache initialization."""
        cache = SemanticCache(temp_db)
        
        assert cache.db_path == temp_db
        assert os.path.exists(temp_db)
        assert cache.index_loaded
    
    def test_generate_query_hash(self, cache):
        """Test query hash generation."""
        query = "What is VA disability?"
        hash1 = cache._generate_query_hash(query)
        hash2 = cache._generate_query_hash(query)
        
        assert hash1 == hash2  # Same query should produce same hash
        assert len(hash1) == 16  # Expected hash length
        
        # Different queries should produce different hashes
        different_query = "How to apply for benefits?"
        hash3 = cache._generate_query_hash(different_query)
        assert hash1 != hash3
    
    def test_store_and_retrieve_exact(self, cache, sample_answer_result):
        """Test storing and retrieving exact cache matches."""
        query = "What is VA disability?"
        top_doc_ids = ['doc-1', 'doc-2']
        token_usage = {'total_tokens': 150}
        
        # Store in cache
        cache.store(query, top_doc_ids, sample_answer_result, token_usage)
        
        # Retrieve exact match
        cache_hit = cache.retrieve(query, top_doc_ids)
        
        assert cache_hit is not None
        assert cache_hit.hit_type == 'exact'
        assert cache_hit.similarity == 1.0
        assert cache_hit.entry.normalized_query == query.lower()
        assert cache_hit.entry.answer_result.answer_plain == sample_answer_result.answer_plain
    
    def test_retrieve_no_match(self, cache):
        """Test retrieving with no cache match."""
        query = "Nonexistent query"
        top_doc_ids = ['doc-1']
        
        cache_hit = cache.retrieve(query, top_doc_ids)
        
        assert cache_hit is None
    
    def test_semantic_matching(self, cache, sample_answer_result, mock_openai):
        """Test semantic similarity matching."""
        # Store original query
        original_query = "What is VA disability compensation?"
        top_doc_ids = ['doc-1', 'doc-2']
        token_usage = {'total_tokens': 150}
        
        cache.store(original_query, top_doc_ids, sample_answer_result, token_usage)
        
        # Try similar query with high similarity
        similar_query = "What is veterans disability compensation?"
        
        # Mock high similarity in FAISS search
        with patch.object(cache, '_find_semantic_matches') as mock_search:
            mock_search.return_value = [(cache._generate_query_hash(original_query), 0.95)]
            
            cache_hit = cache.retrieve(similar_query, top_doc_ids)
            
            assert cache_hit is not None
            assert cache_hit.hit_type == 'semantic'
            assert cache_hit.similarity == 0.95
    
    def test_cache_validation_jaccard_threshold(self, cache, sample_answer_result):
        """Test cache validation with Jaccard threshold."""
        query = "What is VA disability?"
        original_doc_ids = ['doc-1', 'doc-2', 'doc-3']
        token_usage = {'total_tokens': 150}
        
        # Store in cache
        cache.store(query, original_doc_ids, sample_answer_result, token_usage)
        
        # Try to retrieve with very different doc IDs (low Jaccard similarity)
        different_doc_ids = ['doc-4', 'doc-5', 'doc-6']
        
        cache_hit = cache.retrieve(query, different_doc_ids)
        
        # Should not return hit due to low Jaccard similarity
        assert cache_hit is None
    
    def test_cache_validation_jaccard_pass(self, cache, sample_answer_result):
        """Test cache validation with sufficient Jaccard similarity."""
        query = "What is VA disability?"
        original_doc_ids = ['doc-1', 'doc-2', 'doc-3']
        token_usage = {'total_tokens': 150}
        
        # Store in cache
        cache.store(query, original_doc_ids, sample_answer_result, token_usage)
        
        # Try to retrieve with overlapping doc IDs (good Jaccard similarity)
        overlapping_doc_ids = ['doc-1', 'doc-2', 'doc-4']  # 2/3 overlap
        
        cache_hit = cache.retrieve(query, overlapping_doc_ids)
        
        # Should return hit due to sufficient Jaccard similarity
        assert cache_hit is not None
        assert cache_hit.hit_type == 'exact'
    
    def test_doc_version_salt_invalidation(self, cache, sample_answer_result):
        """Test cache invalidation when doc version salt changes."""
        query = "What is VA disability?"
        top_doc_ids = ['doc-1', 'doc-2']
        token_usage = {'total_tokens': 150}
        
        # Store with current salt
        cache.store(query, top_doc_ids, sample_answer_result, token_usage)
        
        # Verify it's stored
        cache_hit = cache.retrieve(query, top_doc_ids)
        assert cache_hit is not None
        
        # Change doc version salt
        with patch('app.config.config.doc_version_salt', 'new_salt'):
            cache_hit = cache.retrieve(query, top_doc_ids)
            assert cache_hit is None  # Should be invalidated
    
    def test_get_stats(self, cache, sample_answer_result):
        """Test cache statistics."""
        # Initially empty
        stats = cache.get_stats()
        assert stats['current_version_entries'] == 0
        
        # Add some entries
        for i in range(3):
            query = f"Test query {i}"
            cache.store(query, ['doc-1'], sample_answer_result, {'total_tokens': 100})
        
        stats = cache.get_stats()
        assert stats['current_version_entries'] == 3
        assert stats['estimated_tokens_saved'] > 0
    
    def test_clear_old_entries(self, cache, sample_answer_result):
        """Test clearing old cache entries."""
        # Add entries
        for i in range(3):
            query = f"Test query {i}"
            cache.store(query, ['doc-1'], sample_answer_result, {'total_tokens': 100})
        
        stats_before = cache.get_stats()
        assert stats_before['current_version_entries'] == 3
        
        # Clear entries (keeping current version)
        deleted_count = cache.clear_old_entries(keep_current_version=True)
        assert deleted_count == 0  # No old versions to delete
        
        # Clear all entries
        deleted_count = cache.clear_old_entries(keep_current_version=False)
        assert deleted_count == 3
        
        stats_after = cache.get_stats()
        assert stats_after['current_version_entries'] == 0
    
    def test_faiss_index_operations(self, cache, mock_openai):
        """Test FAISS index operations."""
        # Test adding to empty index
        embedding = [0.1] * 1536  # Standard embedding dimension
        query_hash = "test_hash"
        
        cache._add_to_faiss_index(embedding, query_hash)
        
        assert cache.faiss_index is not None
        assert cache.faiss_index.ntotal == 1
        assert 0 in cache.embedding_to_hash
        assert cache.embedding_to_hash[0] == query_hash
    
    def test_serialization(self, cache, sample_answer_result):
        """Test answer result serialization/deserialization."""
        # Test serialization
        serialized = cache._serialize_answer_result(sample_answer_result)
        assert isinstance(serialized, str)
        
        # Test deserialization
        deserialized = cache._deserialize_answer_result(serialized)
        
        assert deserialized.answer_plain == sample_answer_result.answer_plain
        assert deserialized.answer_html == sample_answer_result.answer_html
        assert len(deserialized.citations) == len(sample_answer_result.citations)
        assert deserialized.citations[0].n == sample_answer_result.citations[0].n
        assert deserialized.citations[0].url == sample_answer_result.citations[0].url
        assert deserialized.status == sample_answer_result.status
