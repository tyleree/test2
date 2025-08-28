"""
Tests for output format validation and API response shape.
"""

import pytest
import json
from unittest.mock import Mock, patch

class TestOutputShape:
    """Test API output formats and validation."""
    
    def test_ask_endpoint_response_structure(self, client, mock_openai, mock_pinecone, mock_sentence_transformers):
        """Test /ask endpoint returns correct JSON structure."""
        
        # Mock successful pipeline responses
        mock_openai.return_value.chat.completions.create.return_value.choices[0].message.content = json.dumps({
            "quotes": [
                {
                    "text": "Veterans are entitled to disability compensation.",
                    "source_url": "https://example.com/benefits",
                    "source_title": "VA Benefits Guide",
                    "source_section": "Overview"
                }
            ],
            "sources": [
                {
                    "url": "https://example.com/benefits",
                    "title": "VA Benefits Guide"
                }
            ]
        })
        
        # Mock answer generation
        answer_response = json.dumps({
            "answer_plain": "Veterans are entitled to disability compensation [1].",
            "answer_html": "<p>Veterans are entitled to disability compensation [1].</p><p><strong>Sources</strong></p><ol><li><a href='https://example.com/benefits'>[1] VA Benefits Guide</a></li></ol>",
            "citations": [
                {"n": 1, "url": "https://example.com/benefits", "title": "VA Benefits Guide"}
            ]
        })
        
        # Set up mock to return different responses for compression vs answer
        def mock_chat_side_effect(*args, **kwargs):
            mock_response = Mock()
            mock_response.usage = Mock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
            
            # Check if this is the answer generation call (uses model_big)
            if kwargs.get('model') == 'gpt-4o':  # model_big
                mock_response.choices = [Mock(message=Mock(content=answer_response))]
            else:  # compression call (model_small)
                mock_response.choices = [Mock(message=Mock(content=json.dumps({
                    "quotes": [
                        {
                            "text": "Veterans are entitled to disability compensation.",
                            "source_url": "https://example.com/benefits",
                            "source_title": "VA Benefits Guide",
                            "source_section": "Overview"
                        }
                    ],
                    "sources": [
                        {
                            "url": "https://example.com/benefits",
                            "title": "VA Benefits Guide"
                        }
                    ]
                })))]
            
            return mock_response
        
        mock_openai.return_value.chat.completions.create.side_effect = mock_chat_side_effect
        
        # Make request
        response = client.post('/api/ask', 
                            json={'question': 'What are VA disability benefits?'},
                            content_type='application/json')
        
        assert response.status_code == 200
        
        data = response.get_json()
        
        # Check required fields
        required_fields = [
            'answer_plain', 'answer_html', 'citations', 
            'cache_mode', 'token_usage', 'latency_ms'
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Check field types
        assert isinstance(data['answer_plain'], str)
        assert isinstance(data['answer_html'], str)
        assert isinstance(data['citations'], list)
        assert isinstance(data['cache_mode'], str)
        assert isinstance(data['token_usage'], dict)
        assert isinstance(data['latency_ms'], int)
        
        # Check citation structure
        if data['citations']:
            citation = data['citations'][0]
            assert 'n' in citation
            assert 'url' in citation
            assert isinstance(citation['n'], int)
            assert isinstance(citation['url'], str)
    
    def test_ask_endpoint_html_format(self, client, mock_openai, mock_pinecone, mock_sentence_transformers):
        """Test that HTML output follows required format."""
        
        # Mock answer with proper HTML format
        html_answer = """<p>Veterans are entitled to disability compensation based on their service-connected conditions [1].</p>
<p>The amount depends on the disability rating assigned by the VA [1].</p>
<p><strong>Sources</strong></p>
<ol><li><a href='https://example.com/benefits'>[1] VA Benefits Guide</a></li></ol>"""
        
        answer_response = json.dumps({
            "answer_plain": "Veterans are entitled to disability compensation [1].",
            "answer_html": html_answer,
            "citations": [
                {"n": 1, "url": "https://example.com/benefits", "title": "VA Benefits Guide"}
            ]
        })
        
        def mock_chat_side_effect(*args, **kwargs):
            mock_response = Mock()
            mock_response.usage = Mock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
            
            if kwargs.get('model') == 'gpt-4o':  # Answer generation
                mock_response.choices = [Mock(message=Mock(content=answer_response))]
            else:  # Compression
                mock_response.choices = [Mock(message=Mock(content=json.dumps({
                    "quotes": [{"text": "Test quote", "source_url": "https://example.com/benefits"}],
                    "sources": [{"url": "https://example.com/benefits", "title": "Test"}]
                })))]
            
            return mock_response
        
        mock_openai.return_value.chat.completions.create.side_effect = mock_chat_side_effect
        
        response = client.post('/api/ask',
                            json={'question': 'What are VA disability benefits?'},
                            content_type='application/json')
        
        assert response.status_code == 200
        data = response.get_json()
        
        html = data['answer_html']
        
        # Check HTML structure
        assert '<p>' in html
        assert '</p>' in html
        assert '<strong>Sources</strong>' in html
        assert '<ol>' in html
        assert '<li>' in html
        assert '<a href=' in html
        
        # Check citation format
        assert '[1]' in html
        
        # Check no forbidden tags (basic check)
        forbidden_tags = ['<script>', '<style>', '<iframe>', '<object>']
        for tag in forbidden_tags:
            assert tag not in html.lower()
    
    def test_ask_endpoint_citations_numbered(self, client, mock_openai, mock_pinecone, mock_sentence_transformers):
        """Test that citations are properly numbered."""
        
        answer_response = json.dumps({
            "answer_plain": "First fact [1]. Second fact [2]. Third fact [1].",
            "answer_html": "<p>First fact [1]. Second fact [2]. Third fact [1].</p><p><strong>Sources</strong></p><ol><li><a href='https://example.com/1'>[1] Source One</a></li><li><a href='https://example.com/2'>[2] Source Two</a></li></ol>",
            "citations": [
                {"n": 1, "url": "https://example.com/1", "title": "Source One"},
                {"n": 2, "url": "https://example.com/2", "title": "Source Two"}
            ]
        })
        
        def mock_chat_side_effect(*args, **kwargs):
            mock_response = Mock()
            mock_response.usage = Mock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
            
            if kwargs.get('model') == 'gpt-4o':
                mock_response.choices = [Mock(message=Mock(content=answer_response))]
            else:
                mock_response.choices = [Mock(message=Mock(content=json.dumps({
                    "quotes": [
                        {"text": "Quote 1", "source_url": "https://example.com/1"},
                        {"text": "Quote 2", "source_url": "https://example.com/2"}
                    ],
                    "sources": [
                        {"url": "https://example.com/1", "title": "Source One"},
                        {"url": "https://example.com/2", "title": "Source Two"}
                    ]
                })))]
            
            return mock_response
        
        mock_openai.return_value.chat.completions.create.side_effect = mock_chat_side_effect
        
        response = client.post('/api/ask',
                            json={'question': 'Tell me about benefits'},
                            content_type='application/json')
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Check citations are numbered sequentially
        citations = data['citations']
        citation_numbers = [c['n'] for c in citations]
        
        assert len(set(citation_numbers)) == len(citation_numbers)  # No duplicates
        assert min(citation_numbers) == 1  # Starts at 1
        assert max(citation_numbers) == len(citations)  # Sequential
    
    def test_ask_endpoint_error_handling(self, client):
        """Test error handling in /ask endpoint."""
        
        # Test missing question
        response = client.post('/api/ask',
                            json={},
                            content_type='application/json')
        assert response.status_code == 400
        assert 'error' in response.get_json()
        
        # Test empty question
        response = client.post('/api/ask',
                            json={'question': ''},
                            content_type='application/json')
        assert response.status_code == 400
        
        # Test non-JSON request
        response = client.post('/api/ask',
                            data='not json',
                            content_type='text/plain')
        assert response.status_code == 400
    
    def test_health_check_response(self, client):
        """Test health check endpoint response format."""
        response = client.get('/api/healthz')
        
        # Should return 200 or 503 depending on component status
        assert response.status_code in [200, 503]
        
        data = response.get_json()
        
        # Check required fields
        assert 'status' in data
        assert 'components' in data
        assert 'config' in data
        
        # Check status values
        assert data['status'] in ['healthy', 'degraded', 'unhealthy']
        
        # Check components structure
        components = data['components']
        expected_components = [
            'retriever', 'reranker', 'compressor', 
            'answer_generator', 'semantic_cache'
        ]
        for component in expected_components:
            assert component in components
            assert isinstance(components[component], bool)
    
    def test_metrics_endpoint_response(self, client):
        """Test metrics endpoint response format."""
        response = client.get('/api/metrics')
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Check main sections
        assert 'performance' in data
        assert 'hourly_breakdown' in data
        assert 'cache_stats' in data
        assert 'timestamp' in data
        
        # Check performance structure
        performance = data['performance']
        assert 'overview' in performance
        assert 'efficiency' in performance
        assert 'latency' in performance
        assert 'quality' in performance
        
        # Check hourly breakdown is a list
        assert isinstance(data['hourly_breakdown'], list)
    
    def test_debug_endpoints_response(self, client):
        """Test debug endpoints return proper structure."""
        debug_endpoints = [
            '/api/debug/retrieval',
            '/api/debug/rerank', 
            '/api/debug/quotes',
            '/api/debug/cache'
        ]
        
        for endpoint in debug_endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200
            
            data = response.get_json()
            assert isinstance(data, dict)
            
            # Should have either debug data or a message
            assert len(data) > 0
