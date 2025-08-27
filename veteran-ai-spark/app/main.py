"""
FastAPI main application for RAG pipeline with multi-layer semantic caching.
"""

import logging
import os
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .settings import settings
from .schemas import (
    AskRequest, AnswerPayload, CacheStatsResponse, ClearCacheRequest, 
    ClearCacheResponse, HealthResponse, MetricsData
)
from .pipeline import pipeline
from .cache import cache
from .metrics import metrics
from .validators import validator
from .timeline import timeline

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="RAG Pipeline API",
    description="FastAPI RAG pipeline with multi-layer semantic caching",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency for admin authentication
def verify_admin_token(
    x_admin_token: str = Header(None),
    token: str = Query(None)
) -> bool:
    """Verify admin token for protected endpoints. Accepts token via header or query parameter."""
    if not settings.admin_token:
        # For development, allow access if no admin token is configured
        return True
    
    # Check both header and query parameter
    provided_token = x_admin_token or token
    
    if provided_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    
    return True


@app.get("/healthz", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    try:
        # Check if cache DB exists
        cache_db_exists = os.path.exists(settings.cache_db_path)
        
        # Check if FAISS index exists
        faiss_index_exists = os.path.exists(settings.faiss_path)
        
        return HealthResponse(
            status="ok",
            version="1.0.0",
            cache_db_exists=cache_db_exists,
            faiss_index_exists=faiss_index_exists
        )
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail="Health check failed")


@app.post("/ask", response_model=AnswerPayload)
async def ask_question(request: AskRequest):
    """
    Ask a question and get an answer with citations.
    
    This is the main endpoint that processes questions through the RAG pipeline
    with multi-layer semantic caching for optimal performance and cost efficiency.
    """
    try:
        logger.info(f"Received question: {request.question[:100]}...")
        
        # Process through pipeline
        result = await pipeline.answer_question(
            question=request.question,
            detail_level=request.detail
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Question processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process question: {str(e)}")


@app.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """Get cache statistics and performance metrics."""
    try:
        # Get cache stats
        cache_stats = cache.get_stats()
        
        # Calculate hit rate
        total_hits = cache_stats.get("total_hits", 0)
        never_hit = cache_stats.get("never_hit", 0)
        total_entries = cache_stats.get("total_entries", 0)
        
        hit_rate = 0.0
        if total_entries > 0:
            hit_rate = (total_hits / max(total_hits + never_hit, 1)) * 100
        
        from .schemas import CacheStats
        stats = CacheStats(
            total_entries=total_entries,
            exact_hits=0,  # Would need separate tracking
            semantic_hits=total_hits,
            misses=never_hit,
            hit_rate=hit_rate,
            memory_usage_mb=cache_stats.get("memory_usage_mb", 0)
        )
        
        return CacheStatsResponse(stats=stats)
    
    except Exception as e:
        logger.error(f"Cache stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve cache stats")


@app.post("/cache/clear", response_model=ClearCacheResponse)
async def clear_cache(
    request: ClearCacheRequest,
    _: bool = Depends(verify_admin_token)
):
    """
    Clear all cache entries (requires admin token).
    
    This is a dangerous operation that will remove all cached results.
    Use with caution in production environments.
    """
    try:
        if not request.confirm:
            raise HTTPException(status_code=400, detail="Confirmation required")
        
        # Clear cache
        entries_removed = cache.clear_cache()
        
        # Reset metrics
        metrics.reset_metrics()
        
        logger.info(f"Cache cleared: {entries_removed} entries removed")
        
        return ClearCacheResponse(
            cleared=True,
            entries_removed=entries_removed,
            status="success"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cache clearing failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear cache")


@app.get("/metrics")
async def get_metrics():
    """
    Get comprehensive metrics for monitoring and analytics.
    
    Returns detailed performance metrics including cache efficiency,
    token usage, latency statistics, and error rates.
    """
    try:
        # Get current metrics
        current_stats = metrics.get_current_stats()
        cache_efficiency = metrics.get_cache_efficiency_metrics()
        pipeline_stats = pipeline.get_pipeline_stats()
        
        return {
            "status": "ok",
            "timestamp": current_stats.get("uptime_seconds", 0),
            "performance": {
                "total_requests": current_stats["total_requests"],
                "avg_latency_ms": current_stats["avg_latency_ms"],
                "p95_latency_ms": current_stats["latency_p95"],
                "p99_latency_ms": current_stats["latency_p99"],
                "success_rate": current_stats["rolling_window"]["success_rate"]
            },
            "cache": {
                "hit_ratio": cache_efficiency["cache_hit_ratio"],
                "exact_hits": current_stats["exact_cache_hits"],
                "semantic_hits": current_stats["semantic_cache_hits"],
                "misses": current_stats["cache_misses"],
                "efficiency_score": cache_efficiency["efficiency_score"]
            },
            "tokens": {
                "total_big_model": current_stats["total_tokens_big"],
                "total_small_model": current_stats["total_tokens_small"],
                "total_saved": current_stats["total_tokens_saved"],
                "saved_ratio": cache_efficiency["tokens_saved_ratio"],
                "avg_per_request": cache_efficiency["avg_tokens_per_request"]
            },
            "pipeline": pipeline_stats,
            "recent_errors": current_stats["recent_errors"]
        }
    
    except Exception as e:
        logger.error(f"Metrics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics")


@app.get("/admin/analytics")
async def get_admin_analytics(_: bool = Depends(verify_admin_token)):
    """
    Get analytics data formatted for the admin dashboard.
    
    This endpoint provides metrics in the format expected by the existing
    AdminAnalytics React component, allowing seamless integration.
    """
    try:
        # Get RAG pipeline metrics for admin dashboard
        rag_data = metrics.get_admin_analytics_data()
        
        return rag_data
    
    except Exception as e:
        logger.error(f"Admin analytics retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve admin analytics")


@app.get("/admin/timeline")
async def get_timeline(
    limit: int = 100,
    offset: int = 0,
    cache_mode: str = None,
    date_from: str = None,
    date_to: str = None,
    _: bool = Depends(verify_admin_token)
):
    """
    Get comprehensive timeline of all questions and responses.
    
    Query parameters:
    - limit: Maximum number of entries to return (default: 100)
    - offset: Number of entries to skip (default: 0)
    - cache_mode: Filter by cache mode (exact_hit, semantic_hit, miss)
    - date_from: ISO format date string (e.g., "2024-01-01T00:00:00Z")
    - date_to: ISO format date string
    """
    try:
        entries = timeline.get_timeline(
            limit=min(limit, 500),  # Cap at 500 for performance
            offset=offset,
            cache_mode_filter=cache_mode,
            date_from=date_from,
            date_to=date_to
        )
        
        stats = timeline.get_timeline_stats(hours=24)
        
        return {
            "status": "ok",
            "entries": entries,
            "stats": stats,
            "pagination": {
                "limit": limit,
                "offset": offset,
                "total_returned": len(entries)
            }
        }
    
    except Exception as e:
        logger.error(f"Timeline retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve timeline")


@app.get("/admin/timeline/{question_id}")
async def get_question_details(
    question_id: int,
    _: bool = Depends(verify_admin_token)
):
    """Get detailed information for a specific question."""
    try:
        details = timeline.get_question_details(question_id)
        if not details:
            raise HTTPException(status_code=404, detail="Question not found")
        
        return {
            "status": "ok",
            "question": details
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Question details retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve question details")


@app.get("/timeline/stats")
async def get_timeline_stats(hours: int = 24):
    """Get public timeline statistics (no auth required)."""
    try:
        stats = timeline.get_timeline_stats(hours=min(hours, 168))  # Cap at 1 week
        
        return {
            "status": "ok",
            "stats": stats,
            "period_hours": hours
        }
    
    except Exception as e:
        logger.error(f"Timeline stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve timeline stats")


@app.post("/admin/cache/invalidate")
async def force_cache_invalidation(
    _: bool = Depends(verify_admin_token)
):
    """Force cache invalidation (admin only)."""
    try:
        validator.force_invalidate_cache("Manual admin invalidation")
        
        return {
            "status": "success",
            "message": "Cache invalidated successfully"
        }
    
    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to invalidate cache")


@app.get("/pipeline/stats")
async def get_pipeline_stats():
    """Get detailed pipeline statistics and configuration."""
    try:
        stats = pipeline.get_pipeline_stats()
        return {
            "status": "ok",
            "pipeline": stats
        }
    
    except Exception as e:
        logger.error(f"Pipeline stats retrieval failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve pipeline stats")


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {"error": "Endpoint not found", "status_code": 404}


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return {"error": "Internal server error", "status_code": 500}


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize components on startup."""
    logger.info("Starting RAG Pipeline API...")
    logger.info(f"Cache DB: {settings.cache_db_path}")
    logger.info(f"FAISS Index: {settings.faiss_path}")
    logger.info(f"Models: Big={settings.model_big}, Small={settings.model_small}")
    logger.info(f"Similarity threshold: {settings.sim_threshold}")
    logger.info("RAG Pipeline API started successfully")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down RAG Pipeline API...")


if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

