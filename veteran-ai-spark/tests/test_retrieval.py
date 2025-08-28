"""
Tests for retrieval functionality.
"""

import pytest
from unittest.mock import Mock, patch

from app.retrieval import HybridRetriever, RetrievalCandidate

class TestHybridRetriever:
    """Test hybrid retrieval system."""
    
    def test_init(self, mock_openai, mock_pinecone):
        """Test retriever initialization."""
        retriever = HybridRetriever()
        assert retriever.openai_client is not None
        assert retriever.pc is not None
        assert retriever.index is not None
        assert not retriever.corpus_loaded
    
    def test_query_rewriting_simple(self, mock_openai, mock_pinecone):
        """Test that simple queries are not rewritten."""
        retriever = HybridRetriever()
        
        simple_query = "What is VA disability?"
        result = retriever.rewrite_query(simple_query)
        
        assert result == simple_query
        # OpenAI should not be called for simple queries
        mock_openai.return_value.chat.completions.create.assert_not_called()
    
    def test_query_rewriting_complex(self, mock_openai, mock_pinecone):
        """Test that complex queries are rewritten."""
        retriever = HybridRetriever()
        
        # Mock rewrite response
        mock_openai.return_value.chat.completions.create.return_value.choices[0].message.content = "VA disability compensation rates"
        
        complex_query = "What are the current disability compensation rates for veterans who were injured in combat and how do they compare to previous years and what documentation is needed?"
        result = retriever.rewrite_query(complex_query)
        
        assert result == "VA disability compensation rates"
        mock_openai.return_value.chat.completions.create.assert_called_once()
    
    def test_generate_query_embedding(self, mock_openai, mock_pinecone):
        """Test query embedding generation."""
        retriever = HybridRetriever()
        
        query = "test query"
        embedding = retriever.generate_query_embedding(query)
        
        assert isinstance(embedding, list)
        assert len(embedding) == 1536  # Expected dimension
        mock_openai.return_value.embeddings.create.assert_called_once()
    
    def test_vector_search(self, mock_openai, mock_pinecone):
        """Test vector search functionality."""
        retriever = HybridRetriever()
        
        query = "VA disability benefits"
        candidates = retriever.vector_search(query)
        
        assert len(candidates) == 1  # Based on mock response
        assert isinstance(candidates[0], RetrievalCandidate)
        assert candidates[0].chunk_id == 'test-chunk-1'
        assert candidates[0].text == 'Test document content'
        assert candidates[0].source_url == 'https://example.com/test'
    
    def test_vector_search_no_results(self, mock_openai, mock_pinecone):
        """Test vector search with no results."""
        # Mock empty response
        mock_pinecone.return_value.Index.return_value.query.return_value = {'matches': []}
        
        retriever = HybridRetriever()
        candidates = retriever.vector_search("nonexistent query")
        
        assert len(candidates) == 0
    
    def test_vector_search_incomplete_metadata(self, mock_openai, mock_pinecone):
        """Test vector search with incomplete metadata."""
        # Mock response with incomplete metadata
        mock_pinecone.return_value.Index.return_value.query.return_value = {
            'matches': [
                {
                    'id': 'incomplete-chunk',
                    'score': 0.9,
                    'metadata': {
                        'text': 'Some text'
                        # Missing required fields: source_url, doc_id
                    }
                }
            ]
        }
        
        retriever = HybridRetriever()
        candidates = retriever.vector_search("test query")
        
        assert len(candidates) == 0  # Should be filtered out
    
    def test_load_bm25_corpus(self, mock_openai, mock_pinecone):
        """Test BM25 corpus loading."""
        retriever = HybridRetriever()
        retriever.load_bm25_corpus()
        
        assert retriever.corpus_loaded
        assert len(retriever.bm25_corpus) == 1  # Based on mock response
        assert retriever.bm25_model is not None
    
    def test_bm25_search(self, mock_openai, mock_pinecone):
        """Test BM25 search functionality."""
        retriever = HybridRetriever()
        retriever.load_bm25_corpus()
        
        query = "test document"
        results = retriever.bm25_search(query)
        
        assert isinstance(results, list)
        # Results depend on BM25 scoring, just check structure
        for idx, score in results:
            assert isinstance(idx, (int, np.integer))
            assert isinstance(score, (float, np.floating))
    
    def test_merge_search_results(self, mock_openai, mock_pinecone, sample_retrieval_candidates):
        """Test merging of vector and BM25 results."""
        retriever = HybridRetriever()
        
        # Mock BM25 results
        bm25_results = [(0, 0.5), (1, 0.3)]
        
        # Mock BM25 metadata
        retriever.bm25_metadata = [
            {
                'chunk_id': 'chunk-1',
                'doc_id': 'doc-1',
                'text': 'Test text 1',
                'source_url': 'https://example.com/1'
            },
            {
                'chunk_id': 'chunk-3',
                'doc_id': 'doc-3',
                'text': 'Test text 3',
                'source_url': 'https://example.com/3'
            }
        ]
        
        merged = retriever.merge_search_results(sample_retrieval_candidates, bm25_results)
        
        assert len(merged) >= len(sample_retrieval_candidates)
        # Check that scores are combined
        for candidate in merged:
            assert candidate.combined_score > 0
    
    def test_retrieve_full_pipeline(self, mock_openai, mock_pinecone):
        """Test full retrieval pipeline."""
        retriever = HybridRetriever()
        
        query = "VA disability benefits"
        candidates = retriever.retrieve(query)
        
        assert isinstance(candidates, list)
        assert len(candidates) > 0
        assert all(isinstance(c, RetrievalCandidate) for c in candidates)
    
    def test_get_debug_info(self, mock_openai, mock_pinecone):
        """Test debug information retrieval."""
        retriever = HybridRetriever()
        
        debug_info = retriever.get_debug_info()
        
        assert isinstance(debug_info, dict)
        assert 'corpus_loaded' in debug_info
        assert 'pinecone_index' in debug_info
        assert 'retrieval_top_k' in debug_info
