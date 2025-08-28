"""
Pytest configuration and fixtures.
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch

from app.factory import create_app
from app.config import config

@pytest.fixture
def app():
    """Create test Flask application."""
    # Override config for testing
    test_config = {
        'TESTING': True,
        'DEBUG': True,
        'SECRET_KEY': 'test-secret-key'
    }
    
    app = create_app(test_config)
    return app

@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()

@pytest.fixture
def temp_db():
    """Create temporary database file."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    if os.path.exists(temp_path):
        os.unlink(temp_path)

@pytest.fixture
def mock_openai():
    """Mock OpenAI API responses."""
    with patch('openai.OpenAI') as mock_client:
        # Mock embedding response
        mock_embedding = Mock()
        mock_embedding.data = [Mock(embedding=[0.1] * 1536)]
        mock_client.return_value.embeddings.create.return_value = mock_embedding
        
        # Mock chat completion response
        mock_completion = Mock()
        mock_completion.choices = [Mock(message=Mock(content='{"test": "response"}'))]
        mock_completion.usage = Mock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )
        mock_client.return_value.chat.completions.create.return_value = mock_completion
        
        yield mock_client

@pytest.fixture
def mock_pinecone():
    """Mock Pinecone client."""
    with patch('pinecone.Pinecone') as mock_pc:
        mock_index = Mock()
        mock_index.query.return_value = {
            'matches': [
                {
                    'id': 'test-chunk-1',
                    'score': 0.9,
                    'metadata': {
                        'text': 'Test document content',
                        'title': 'Test Document',
                        'section': 'Test Section',
                        'source_url': 'https://example.com/test',
                        'doc_id': 'test-doc-1',
                        'chunk_id': 'test-chunk-1',
                        'token_count': 50
                    }
                }
            ]
        }
        mock_index.describe_index_stats.return_value = {'total_vector_count': 1000}
        
        mock_pc.return_value.Index.return_value = mock_index
        yield mock_pc

@pytest.fixture
def mock_sentence_transformers():
    """Mock sentence transformers."""
    with patch('sentence_transformers.CrossEncoder') as mock_encoder:
        mock_encoder.return_value.predict.return_value = [0.8, 0.7, 0.6]
        yield mock_encoder

@pytest.fixture
def sample_retrieval_candidates():
    """Sample retrieval candidates for testing."""
    from app.retrieval import RetrievalCandidate
    
    return [
        RetrievalCandidate(
            chunk_id='chunk-1',
            doc_id='doc-1',
            text='This is a test document about VA benefits.',
            title='VA Benefits Guide',
            section='Overview',
            source_url='https://example.com/benefits',
            vector_score=0.9,
            bm25_score=0.8,
            combined_score=0.85,
            token_count=50
        ),
        RetrievalCandidate(
            chunk_id='chunk-2',
            doc_id='doc-2',
            text='Information about disability ratings and compensation.',
            title='Disability Ratings',
            section='Compensation',
            source_url='https://example.com/disability',
            vector_score=0.8,
            bm25_score=0.7,
            combined_score=0.75,
            token_count=45
        )
    ]

@pytest.fixture
def sample_quotes():
    """Sample quotes for testing."""
    from app.compress import Quote
    
    return [
        Quote(
            text='Veterans are entitled to disability compensation.',
            source_url='https://example.com/benefits',
            title='VA Benefits Guide',
            section='Overview',
            chunk_id='chunk-1',
            token_count=25
        ),
        Quote(
            text='Ratings are based on severity of condition.',
            source_url='https://example.com/disability',
            title='Disability Ratings',
            section='Compensation',
            chunk_id='chunk-2',
            token_count=20
        )
    ]
