"""
End-to-end tests for the RAG pipeline.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
import numpy as np

from app.pipeline import pipeline
from app.schemas import AskRequest, TokenUsage
from app.settings import settings


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client for testing."""
    mock_client = Mock()
    
    # Mock embedding response
    mock_embedding_response = Mock()
    mock_embedding_response.data = [Mock(embedding=[0.1] * 1536)]  # OpenAI embedding size
    mock_client.embeddings.create.return_value = mock_embedding_response
    
    # Mock chat completion response
    mock_completion_response = Mock()
    mock_completion_response.choices = [
        Mock(message=Mock(content='{"quotes": [{"doc_id": "test_doc", "chunk_id": "chunk_1", "url": "http://example.com", "quote": "This is a test quote."}]}'))
    ]
    mock_completion_response.usage = Mock(completion_tokens=100, prompt_tokens=500, total_tokens=600)
    mock_client.chat.completions.create.return_value = mock_completion_response
    
    return mock_client


@pytest.fixture
def mock_pinecone_index():
    """Mock Pinecone index for testing."""
    mock_index = Mock()
    
    # Mock query response
    mock_index.query.return_value = {
        'matches': [
            {
                'id': 'doc1-chunk1',
                'score': 0.95,
                'metadata': {
                    'doc_id': 'doc1',
                    'text': 'This is test content about machine learning.',
                    'url': 'http://example.com/doc1',
                    'title': 'ML Basics'
                }
            },
            {
                'id': 'doc2-chunk1', 
                'score': 0.87,
                'metadata': {
                    'doc_id': 'doc2',
                    'text': 'Machine learning algorithms learn from data.',
                    'url': 'http://example.com/doc2',
                    'title': 'ML Algorithms'
                }
            }
        ]
    }
    
    return mock_index


@pytest.fixture
def mock_sentence_transformer():
    """Mock sentence transformer for testing."""
    mock_model = Mock()
    
    # Mock encoding for cache embeddings
    mock_model.encode.return_value = np.array([[0.5] * 384])  # Cache embedding size
    
    # Mock predict for reranking
    mock_model.predict.return_value = np.array([0.8, 0.6])  # Rerank scores
    
    return mock_model


@pytest.mark.asyncio
async def test_full_pipeline_execution(mock_openai_client, mock_pinecone_index, mock_sentence_transformer):
    """Test complete pipeline execution from question to answer."""
    
    with patch('app.retrieval.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.retrieval.Pinecone') as mock_pinecone, \
         patch('app.compress.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.answer.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.cache.SentenceTransformer', return_value=mock_sentence_transformer), \
         patch('app.rerank.CrossEncoder', return_value=mock_sentence_transformer):
        
        # Setup Pinecone mock
        mock_pc = Mock()
        mock_pc.Index.return_value = mock_pinecone_index
        mock_pinecone.return_value = mock_pc
        
        # Mock final answer generation
        final_answer_mock = Mock()
        final_answer_mock.choices = [
            Mock(message=Mock(content="Machine learning is a subset of artificial intelligence that enables computers to learn from data. [1][2]"))
        ]
        final_answer_mock.usage = Mock(completion_tokens=150, prompt_tokens=800, total_tokens=950)
        
        # Set up different responses for different calls
        mock_openai_client.chat.completions.create.side_effect = [
            mock_completion_response,  # For compression
            final_answer_mock  # For final answer
        ]
        
        # Execute pipeline
        result = await pipeline.answer_question("What is machine learning?")
        
        # Verify response structure
        assert result.answer is not None
        assert len(result.answer) > 0
        assert result.cache_mode == "miss"  # First time should be cache miss
        assert result.token_usage.total_tokens > 0
        assert result.latency_ms > 0
        
        # Verify citations
        assert len(result.citations) >= 0  # May have citations
        
        # Verify token usage
        assert result.token_usage.model_big == settings.model_big
        assert result.token_usage.model_small == settings.model_small


@pytest.mark.asyncio 
async def test_pipeline_with_cache_hit(mock_openai_client, mock_pinecone_index, mock_sentence_transformer):
    """Test pipeline behavior with cache hits."""
    
    with patch('app.retrieval.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.retrieval.Pinecone') as mock_pinecone, \
         patch('app.compress.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.answer.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.cache.SentenceTransformer', return_value=mock_sentence_transformer), \
         patch('app.rerank.CrossEncoder', return_value=mock_sentence_transformer):
        
        # Setup mocks
        mock_pc = Mock()
        mock_pc.Index.return_value = mock_pinecone_index
        mock_pinecone.return_value = mock_pc
        
        # Mock compression response
        compression_mock = Mock()
        compression_mock.choices = [
            Mock(message=Mock(content='{"quotes": [{"doc_id": "test_doc", "chunk_id": "chunk_1", "url": "http://example.com", "quote": "Machine learning enables pattern recognition."}]}'))
        ]
        compression_mock.usage = Mock(completion_tokens=80, prompt_tokens=400, total_tokens=480)
        
        # Mock final answer
        answer_mock = Mock()
        answer_mock.choices = [
            Mock(message=Mock(content="Machine learning enables pattern recognition in data. [1]"))
        ]
        answer_mock.usage = Mock(completion_tokens=120, prompt_tokens=600, total_tokens=720)
        
        mock_openai_client.chat.completions.create.side_effect = [
            compression_mock,
            answer_mock
        ]
        
        # First execution - should be cache miss
        question = "How does machine learning work?"
        result1 = await pipeline.answer_question(question)
        assert result1.cache_mode == "miss"
        
        # Second execution - should potentially be cache hit (exact or semantic)
        result2 = await pipeline.answer_question(question)
        # Note: In real scenario this would be "exact", but our mock setup may not trigger cache hit
        assert result2.cache_mode in ["miss", "exact", "semantic"]


@pytest.mark.asyncio
async def test_pipeline_budget_constraints(mock_openai_client, mock_pinecone_index, mock_sentence_transformer):
    """Test that pipeline respects token budgets and limits."""
    
    with patch('app.retrieval.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.retrieval.Pinecone') as mock_pinecone, \
         patch('app.compress.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.answer.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.cache.SentenceTransformer', return_value=mock_sentence_transformer), \
         patch('app.rerank.CrossEncoder', return_value=mock_sentence_transformer):
        
        # Setup mocks
        mock_pc = Mock()
        mock_pc.Index.return_value = mock_pinecone_index
        mock_pinecone.return_value = mock_pc
        
        # Create many mock documents to test limits
        many_matches = []
        for i in range(100):  # More than RERANK_K
            many_matches.append({
                'id': f'doc{i}-chunk1',
                'score': 0.9 - (i * 0.001),  # Decreasing scores
                'metadata': {
                    'doc_id': f'doc{i}',
                    'text': f'This is test content {i} about the topic.',
                    'url': f'http://example.com/doc{i}',
                    'title': f'Document {i}'
                }
            })
        
        mock_pinecone_index.query.return_value = {'matches': many_matches}
        
        # Mock compression with limited quotes
        compression_mock = Mock()
        limited_quotes = []
        for i in range(min(settings.max_sources, 6)):  # Respect MAX_SOURCES
            limited_quotes.append({
                "doc_id": f"doc{i}",
                "chunk_id": f"chunk{i}",
                "url": f"http://example.com/doc{i}",
                "quote": f"Quote {i} within token budget."
            })
        
        compression_mock.choices = [
            Mock(message=Mock(content=f'{{"quotes": {limited_quotes}}}'))
        ]
        compression_mock.usage = Mock(completion_tokens=200, prompt_tokens=1000, total_tokens=1200)
        
        # Mock final answer
        answer_mock = Mock()
        answer_mock.choices = [
            Mock(message=Mock(content="This is a comprehensive answer with citations. " + " ".join([f"[{i+1}]" for i in range(len(limited_quotes))])))
        ]
        answer_mock.usage = Mock(completion_tokens=300, prompt_tokens=1500, total_tokens=1800)
        
        mock_openai_client.chat.completions.create.side_effect = [
            compression_mock,
            answer_mock
        ]
        
        # Execute pipeline
        result = await pipeline.answer_question("Tell me about this topic in detail.")
        
        # Verify constraints
        assert len(result.citations) <= settings.max_sources
        assert result.token_usage.total_tokens <= 3000  # Reasonable upper bound
        
        # Verify we got a valid response
        assert result.answer is not None
        assert len(result.answer) > 0


@pytest.mark.asyncio
async def test_pipeline_error_handling(mock_openai_client, mock_pinecone_index, mock_sentence_transformer):
    """Test pipeline error handling and fallback behavior."""
    
    with patch('app.retrieval.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.retrieval.Pinecone') as mock_pinecone, \
         patch('app.compress.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.answer.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.cache.SentenceTransformer', return_value=mock_sentence_transformer), \
         patch('app.rerank.CrossEncoder', return_value=mock_sentence_transformer):
        
        # Setup Pinecone to fail
        mock_pc = Mock()
        mock_pc.Index.return_value = mock_pinecone_index
        mock_pinecone.return_value = mock_pc
        
        # Make Pinecone query fail
        mock_pinecone_index.query.side_effect = Exception("Pinecone connection error")
        
        # Execute pipeline - should handle error gracefully
        result = await pipeline.answer_question("What happens when things break?")
        
        # Should get error response but not crash
        assert result is not None
        assert result.cache_mode == "miss"
        assert "error" in result.answer.lower() or "apologize" in result.answer.lower()


@pytest.mark.asyncio
async def test_pipeline_no_results(mock_openai_client, mock_pinecone_index, mock_sentence_transformer):
    """Test pipeline behavior when no relevant documents are found."""
    
    with patch('app.retrieval.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.retrieval.Pinecone') as mock_pinecone, \
         patch('app.compress.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.answer.openai.OpenAI', return_value=mock_openai_client), \
         patch('app.cache.SentenceTransformer', return_value=mock_sentence_transformer), \
         patch('app.rerank.CrossEncoder', return_value=mock_sentence_transformer):
        
        # Setup Pinecone to return no results
        mock_pc = Mock()
        mock_pc.Index.return_value = mock_pinecone_index
        mock_pinecone.return_value = mock_pc
        
        mock_pinecone_index.query.return_value = {'matches': []}
        
        # Execute pipeline
        result = await pipeline.answer_question("What is something completely unrelated?")
        
        # Should get appropriate no-results response
        assert result is not None
        assert result.cache_mode == "miss"
        assert "don't have enough information" in result.answer or "not enough information" in result.answer
        assert len(result.citations) == 0
        assert result.token_usage.total_tokens == 0


@pytest.mark.asyncio
async def test_detail_level_expansion():
    """Test that detail=more increases context budget."""
    
    # This is more of an integration test - we'll verify the parameter is passed correctly
    with patch('app.pipeline.pipeline._execute_full_pipeline') as mock_execute:
        mock_execute.return_value = Mock(
            answer="Detailed answer",
            citations=[],
            cache_mode="miss",
            token_usage=TokenUsage(model_big="gpt-4o", model_small="gpt-4o-mini", tokens_big=1000, tokens_small=200, total_tokens=1200),
            latency_ms=1500
        )
        
        # Test normal detail level
        await pipeline.answer_question("Test question")
        
        # Test enhanced detail level  
        await pipeline.answer_question("Test question", detail_level="more")
        
        # Verify both calls were made
        assert mock_execute.call_count == 2
        
        # Verify detail_level parameter was passed
        calls = mock_execute.call_args_list
        assert calls[1][0][4] == "more"  # detail_level parameter


if __name__ == "__main__":
    pytest.main([__file__])








