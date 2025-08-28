#!/usr/bin/env python3
"""
Flask integration module to replace direct Pinecone queries with the new RAG pipeline.
"""

import sys
import os
from time import perf_counter
import asyncio
import json

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.pipeline import pipeline
from app.schemas import AskRequest

def query_new_rag_system(prompt: str) -> dict:
    """
    Query the new RAG system instead of direct Pinecone.
    
    Args:
        prompt: User's question
        
    Returns:
        Dictionary with response data compatible with Flask app
    """
    try:
        print(f"🔥 NEW RAG SYSTEM: Processing query: {prompt[:50]}...")
        
        # Create request object
        request_obj = AskRequest(question=prompt, detail="normal")
        
        # Run the async pipeline
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                pipeline.answer_question(
                    question=prompt,
                    detail_level="normal"
                )
            )
        finally:
            loop.close()
        
        print(f"✅ NEW RAG SYSTEM: Got result with {len(result.citations)} citations")
        
        # Convert to Flask-compatible format
        flask_response = {
            'success': True,
            'content': result.answer,
            'citations': [
                {
                    'text': citation.text if hasattr(citation, 'text') else str(citation),
                    'source_url': citation.source_url if hasattr(citation, 'source_url') else 'https://veteransbenefitskb.com',
                    'score': getattr(citation, 'score', 0.9),
                    'rank': i + 1,
                    'heading': getattr(citation, 'heading', 'VA Benefits Information')
                }
                for i, citation in enumerate(result.citations)
            ],
            'source': 'new_rag_pipeline',
            'metadata': {
                'model': result.token_usage.model_big if result.token_usage else 'gpt-4o',
                'cache_mode': result.cache_mode,
                'latency_ms': result.latency_ms,
                'usage': {
                    'prompt_tokens': getattr(result.token_usage, 'tokens_big', 0) if result.token_usage else 0,
                    'completion_tokens': getattr(result.token_usage, 'tokens_small', 0) if result.token_usage else 0,
                    'total_tokens': getattr(result.token_usage, 'total_tokens', 0) if result.token_usage else 0
                }
            },
            'token_usage': {
                'usage': {
                    'prompt_tokens': getattr(result.token_usage, 'tokens_big', 0) if result.token_usage else 0,
                    'completion_tokens': getattr(result.token_usage, 'tokens_small', 0) if result.token_usage else 0,
                    'total_tokens': getattr(result.token_usage, 'total_tokens', 0) if result.token_usage else 0
                },
                'model': result.token_usage.model_big if result.token_usage else 'gpt-4o',
                'provider': 'new_rag_pipeline'
            }
        }
        
        return flask_response
        
    except Exception as e:
        print(f"❌ NEW RAG SYSTEM ERROR: {e}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc()
        }

def test_medical_expansion():
    """Test the medical expansion with our problem queries."""
    test_queries = [
        "what is the rating for ulnar neuropathy",
        "carpal tunnel syndrome ratings",
        "ptsd rating schedule"
    ]
    
    print("🧪 Testing New RAG System with Medical Expansion")
    print("=" * 60)
    
    for query in test_queries:
        print(f"\n📝 Testing: '{query}'")
        result = query_new_rag_system(query)
        
        if result.get('success'):
            print(f"✅ Success! Answer: {result['content'][:100]}...")
            print(f"📊 Citations: {len(result.get('citations', []))}")
            print(f"🔄 Cache mode: {result['metadata'].get('cache_mode', 'unknown')}")
            print(f"⏱️  Latency: {result['metadata'].get('latency_ms', 0)}ms")
        else:
            print(f"❌ Failed: {result.get('error', 'Unknown error')}")

if __name__ == "__main__":
    test_medical_expansion()
