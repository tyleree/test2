"""
RAG Integration Module

This module provides a drop-in replacement for the Pinecone-based RAG system.
It integrates the new OpenAI-only RAG pipeline with the existing Flask app.

Features:
- Response caching (exact + semantic)
- Streaming responses via Server-Sent Events
- Cache metrics endpoint
"""

import os
import json
from typing import Dict, Any, Optional, Generator
from src.rag_pipeline import (
    RAGPipeline, 
    get_rag_pipeline, 
    initialize_rag_pipeline,
    StreamChunk,
    get_cache_metrics as pipeline_get_cache_metrics
)

# Global RAG pipeline instance
_rag_pipeline: Optional[RAGPipeline] = None
_initialized = False


def init_rag_system() -> bool:
    """
    Initialize the RAG system on app startup.
    
    Returns:
        True if initialization was successful
    """
    global _rag_pipeline, _initialized
    
    if _initialized:
        print("[OK] RAG system already initialized")
        return True
    
    try:
        print("[START] Initializing OpenAI-based RAG system...")
        _rag_pipeline = initialize_rag_pipeline(force_regenerate=False)
        _initialized = True
        print("[OK] RAG system initialized successfully")
        return True
    except Exception as e:
        print(f"[ERROR] RAG system initialization failed: {e}")
        _initialized = False
        return False


def query_rag_system(prompt: str, history: list = None) -> Dict[str, Any]:
    """
    Query the RAG system with a user prompt.
    
    This function provides a compatible interface with the old Pinecone-based system.
    
    Args:
        prompt: User's question
        history: Optional conversation history
        
    Returns:
        Dict with keys:
        - success: bool
        - content: str (the answer)
        - citations: list of source dicts
        - source: str ("openai_rag")
        - metadata: dict with timing and model info
        - error: str (if success is False)
    """
    global _rag_pipeline, _initialized
    
    # Auto-initialize if needed
    if not _initialized or _rag_pipeline is None:
        if not init_rag_system():
            return {
                "success": False,
                "content": "",
                "citations": [],
                "source": "openai_rag",
                "error": "RAG system not initialized",
                "metadata": {}
            }
    
    try:
        # Query the pipeline
        response = _rag_pipeline.ask(prompt, history)
        
        # Format citations for compatibility with existing frontend
        citations = []
        for source in response.sources:
            citation = {
                "id": source.get("id", ""),
                "title": source.get("title", ""),
                "url": source.get("source_url", ""),
                "source_url": source.get("source_url", ""),
                "section": source.get("section", ""),
                "diagnostic_code": source.get("diagnostic_code"),
                "relevance_score": source.get("score", 0)
            }
            citations.append(citation)
        
        return {
            "success": not response.error,
            "content": response.answer,
            "citations": citations,
            "source": "openai_rag",
            "metadata": {
                "model": response.model_used,
                "query_time_ms": response.query_time_ms,
                "chunks_retrieved": response.chunks_retrieved,
                "cache_hit": response.cache_hit,  # "exact", "semantic", "database", "topic", or None
                "semantic_similarity": response.semantic_similarity  # Similarity score (0-1) for cache hits
            },
            "error": response.error,
            "token_usage": {
                "provider": "openai",
                "model": response.model_used,
                "usage": response.token_usage  # Actual token counts from OpenAI API
            },
            # Include question data for analytics
            "question_data": {
                "question": prompt,
                "answer": response.answer,
                "cache_hit": response.cache_hit or "miss",
                "semantic_similarity": response.semantic_similarity,  # Include in analytics
                "sources": citations,
                "chunks_retrieved": response.chunks_retrieved,
                "model_used": response.model_used
            }
        }
        
    except Exception as e:
        print(f"[ERROR] RAG query error: {e}")
        return {
            "success": False,
            "content": "",
            "citations": [],
            "source": "openai_rag",
            "error": str(e),
            "metadata": {}
        }


def get_chunk_by_id(chunk_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific chunk by ID.
    
    Args:
        chunk_id: The chunk/document ID
        
    Returns:
        Chunk dict or None if not found
    """
    global _rag_pipeline
    
    if _rag_pipeline is None:
        return None
    
    return _rag_pipeline.get_chunk_by_id(chunk_id)


def is_rag_ready() -> bool:
    """Check if the RAG system is ready for queries."""
    global _rag_pipeline, _initialized
    return _initialized and _rag_pipeline is not None and _rag_pipeline.is_ready


def query_rag_system_streaming(prompt: str, history: list = None) -> Generator[str, None, None]:
    """
    Query the RAG system with streaming response.
    
    Yields Server-Sent Event formatted strings for each chunk.
    
    Args:
        prompt: User's question
        history: Optional conversation history
        
    Yields:
        SSE-formatted strings (data: {...}\n\n)
    """
    global _rag_pipeline, _initialized
    
    # Auto-initialize if needed
    if not _initialized or _rag_pipeline is None:
        if not init_rag_system():
            yield f"data: {json.dumps({'error': 'RAG system not initialized', 'done': True})}\n\n"
            return
    
    try:
        for chunk in _rag_pipeline.ask_streaming(prompt, history):
            if chunk.error:
                yield f"data: {json.dumps({'error': chunk.error, 'done': True})}\n\n"
                return
            
            if chunk.is_final:
                # Send final chunk with metadata and sources
                final_data = {
                    "done": True,
                    "sources": chunk.sources or [],
                    "metadata": chunk.metadata or {}
                }
                yield f"data: {json.dumps(final_data)}\n\n"
            else:
                # Send content chunk
                yield f"data: {json.dumps({'content': chunk.content, 'done': False})}\n\n"
    
    except Exception as e:
        print(f"[ERROR] RAG streaming error: {e}")
        yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"


def get_cache_metrics() -> Dict[str, Any]:
    """Get response cache metrics."""
    global _rag_pipeline
    
    if _rag_pipeline is None:
        return {"status": "not_initialized"}
    
    return _rag_pipeline.get_cache_metrics()


def clear_response_cache() -> bool:
    """Clear the response cache."""
    global _rag_pipeline
    
    if _rag_pipeline is None:
        return False
    
    _rag_pipeline.clear_cache()
    return True
