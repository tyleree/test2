"""
RAG Integration Module

This module provides a drop-in replacement for the Pinecone-based RAG system.
It integrates the new OpenAI-only RAG pipeline with the existing Flask app.
"""

import os
from typing import Dict, Any, Optional
from src.rag_pipeline import RAGPipeline, get_rag_pipeline, initialize_rag_pipeline

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
        print("\u2705 RAG system already initialized")
        return True
    
    try:
        print("\ud83d\ude80 Initializing OpenAI-based RAG system...")
        _rag_pipeline = initialize_rag_pipeline(force_regenerate=False)
        _initialized = True
        print("\u2705 RAG system initialized successfully")
        return True
    except Exception as e:
        print(f"\u274c RAG system initialization failed: {e}")
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
                "chunks_retrieved": response.chunks_retrieved
            },
            "error": response.error,
            "token_usage": {
                "provider": "openai",
                "model": response.model_used
            }
        }
        
    except Exception as e:
        print(f"\u274c RAG query error: {e}")
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
