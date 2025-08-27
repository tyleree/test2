"""
Metrics collection and monitoring for the RAG pipeline.
Tracks cache performance, token usage, latency, and other key metrics.
"""

import logging
import time
from typing import Dict, Any, List
from dataclasses import dataclass, field
from collections import defaultdict, deque
import threading

logger = logging.getLogger(__name__)


@dataclass
class RequestMetrics:
    """Metrics for a single request."""
    timestamp: float
    cache_mode: str  # "miss", "exact", "semantic"
    latency_ms: int
    tokens_big: int
    tokens_small: int
    saved_tokens: int = 0
    success: bool = True
    error: str = ""


@dataclass
class RollingMetrics:
    """Rolling window metrics."""
    window_size: int = 1000
    requests: deque = field(default_factory=deque)
    
    def add_request(self, request: RequestMetrics):
        """Add request to rolling window."""
        self.requests.append(request)
        if len(self.requests) > self.window_size:
            self.requests.popleft()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics from rolling window."""
        if not self.requests:
            return {
                "total_requests": 0,
                "cache_hit_ratio": 0.0,
                "avg_latency_ms": 0.0,
                "total_tokens": 0,
                "tokens_saved": 0,
                "success_rate": 1.0
            }
        
        total = len(self.requests)
        cache_hits = sum(1 for r in self.requests if r.cache_mode in ["exact", "semantic"])
        exact_hits = sum(1 for r in self.requests if r.cache_mode == "exact")
        semantic_hits = sum(1 for r in self.requests if r.cache_mode == "semantic")
        
        avg_latency = sum(r.latency_ms for r in self.requests) / total
        total_tokens = sum(r.tokens_big + r.tokens_small for r in self.requests)
        total_saved = sum(r.saved_tokens for r in self.requests)
        successes = sum(1 for r in self.requests if r.success)
        
        return {
            "total_requests": total,
            "cache_hit_ratio": cache_hits / total,
            "exact_cache_hits": exact_hits,
            "semantic_cache_hits": semantic_hits,
            "cache_misses": total - cache_hits,
            "avg_latency_ms": avg_latency,
            "total_tokens": total_tokens,
            "tokens_saved": total_saved,
            "success_rate": successes / total,
            "model_usage": self._get_model_usage()
        }
    
    def _get_model_usage(self) -> Dict[str, int]:
        """Get token usage by model type."""
        big_tokens = sum(r.tokens_big for r in self.requests)
        small_tokens = sum(r.tokens_small for r in self.requests)
        
        return {
            "big_model_tokens": big_tokens,
            "small_model_tokens": small_tokens
        }


class MetricsCollector:
    """Centralized metrics collection for the RAG pipeline."""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.rolling_metrics = RollingMetrics()
        self.start_time = time.time()
        
        # Counters
        self.total_requests = 0
        self.exact_cache_hits = 0
        self.semantic_cache_hits = 0
        self.cache_misses = 0
        
        # Token tracking
        self.total_tokens_big = 0
        self.total_tokens_small = 0
        self.total_tokens_saved = 0
        
        # Latency tracking
        self.total_latency_ms = 0
        self.latency_samples = deque(maxlen=1000)
        
        # Model usage tracking
        self.model_usage = defaultdict(int)
        
        # Error tracking
        self.errors = deque(maxlen=100)
    
    def record_request(
        self,
        cache_mode: str,
        latency_ms: int,
        tokens_big: int = 0,
        tokens_small: int = 0,
        saved_tokens: int = 0,
        success: bool = True,
        error: str = ""
    ):
        """Record metrics for a request."""
        with self.lock:
            # Create request metrics
            request = RequestMetrics(
                timestamp=time.time(),
                cache_mode=cache_mode,
                latency_ms=latency_ms,
                tokens_big=tokens_big,
                tokens_small=tokens_small,
                saved_tokens=saved_tokens,
                success=success,
                error=error
            )
            
            # Add to rolling window
            self.rolling_metrics.add_request(request)
            
            # Update counters
            self.total_requests += 1
            self.total_latency_ms += latency_ms
            self.total_tokens_big += tokens_big
            self.total_tokens_small += tokens_small
            self.total_tokens_saved += saved_tokens
            
            # Update cache counters
            if cache_mode == "exact":
                self.exact_cache_hits += 1
            elif cache_mode == "semantic":
                self.semantic_cache_hits += 1
            else:
                self.cache_misses += 1
            
            # Track latency
            self.latency_samples.append(latency_ms)
            
            # Track errors
            if not success and error:
                self.errors.append({
                    "timestamp": time.time(),
                    "error": error,
                    "cache_mode": cache_mode
                })
            
            # Log request
            self._log_request(request)
    
    def record_cache_hit(self, cache_type: str):
        """Record a cache hit."""
        logger.info(f"Cache hit: {cache_type}")
    
    def record_cache_miss(self):
        """Record a cache miss."""
        logger.info("Cache miss")
    
    def _log_request(self, request: RequestMetrics):
        """Log request metrics."""
        logger.info(
            f"Request: cache_mode={request.cache_mode}, "
            f"latency_ms={request.latency_ms}, "
            f"tokens_big={request.tokens_big}, "
            f"tokens_small={request.tokens_small}, "
            f"saved_tokens_estimate={request.saved_tokens}"
        )
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Get current metrics statistics."""
        with self.lock:
            uptime_seconds = time.time() - self.start_time
            
            # Calculate rates
            cache_hit_ratio = 0.0
            avg_latency = 0.0
            
            if self.total_requests > 0:
                total_cache_hits = self.exact_cache_hits + self.semantic_cache_hits
                cache_hit_ratio = total_cache_hits / self.total_requests
                avg_latency = self.total_latency_ms / self.total_requests
            
            # Get rolling window stats
            rolling_stats = self.rolling_metrics.get_stats()
            
            return {
                "uptime_seconds": uptime_seconds,
                "total_requests": self.total_requests,
                "cache_hit_ratio": cache_hit_ratio,
                "exact_cache_hits": self.exact_cache_hits,
                "semantic_cache_hits": self.semantic_cache_hits,
                "cache_misses": self.cache_misses,
                "avg_latency_ms": avg_latency,
                "total_tokens_big": self.total_tokens_big,
                "total_tokens_small": self.total_tokens_small,
                "total_tokens_saved": self.total_tokens_saved,
                "rolling_window": rolling_stats,
                "recent_errors": list(self.errors)[-10:],  # Last 10 errors
                "latency_p95": self._calculate_percentile(95) if self.latency_samples else 0,
                "latency_p99": self._calculate_percentile(99) if self.latency_samples else 0
            }
    
    def _calculate_percentile(self, percentile: int) -> float:
        """Calculate latency percentile."""
        if not self.latency_samples:
            return 0.0
        
        sorted_samples = sorted(self.latency_samples)
        index = int((percentile / 100.0) * len(sorted_samples))
        index = min(index, len(sorted_samples) - 1)
        
        return float(sorted_samples[index])
    
    def get_cache_efficiency_metrics(self) -> Dict[str, Any]:
        """Get cache efficiency specific metrics."""
        with self.lock:
            if self.total_requests == 0:
                return {
                    "cache_hit_ratio": 0.0,
                    "tokens_saved_ratio": 0.0,
                    "avg_tokens_per_request": 0.0,
                    "efficiency_score": 0.0
                }
            
            total_cache_hits = self.exact_cache_hits + self.semantic_cache_hits
            cache_hit_ratio = total_cache_hits / self.total_requests
            
            total_tokens_used = self.total_tokens_big + self.total_tokens_small
            tokens_saved_ratio = (
                self.total_tokens_saved / max(total_tokens_used + self.total_tokens_saved, 1)
            )
            
            avg_tokens_per_request = total_tokens_used / self.total_requests
            
            # Efficiency score combines hit ratio and token savings
            efficiency_score = (cache_hit_ratio * 0.6) + (tokens_saved_ratio * 0.4)
            
            return {
                "cache_hit_ratio": cache_hit_ratio,
                "tokens_saved_ratio": tokens_saved_ratio,
                "avg_tokens_per_request": avg_tokens_per_request,
                "efficiency_score": efficiency_score,
                "total_tokens_saved": self.total_tokens_saved,
                "semantic_hit_rate": (
                    self.semantic_cache_hits / self.total_requests if self.total_requests > 0 else 0
                ),
                "exact_hit_rate": (
                    self.exact_cache_hits / self.total_requests if self.total_requests > 0 else 0
                )
            }
    
    def get_admin_analytics_data(self) -> Dict[str, Any]:
        """
        Get metrics data formatted for the admin analytics dashboard.
        This integrates with the existing AdminAnalytics component.
        """
        current_stats = self.get_current_stats()
        cache_efficiency = self.get_cache_efficiency_metrics()
        
        return {
            "rag_pipeline": {
                "available": True,
                "summary": {
                    "total_requests": current_stats["total_requests"],
                    "cache_hit_ratio": cache_efficiency["cache_hit_ratio"],
                    "avg_latency_ms": current_stats["avg_latency_ms"],
                    "p95_latency_ms": current_stats["latency_p95"],
                    "total_tokens_used": current_stats["total_tokens_big"] + current_stats["total_tokens_small"],
                    "total_tokens_saved": current_stats["total_tokens_saved"],
                    "efficiency_score": cache_efficiency["efficiency_score"]
                },
                "cache_performance": {
                    "exact_hits": current_stats["exact_cache_hits"],
                    "semantic_hits": current_stats["semantic_cache_hits"],
                    "misses": current_stats["cache_misses"],
                    "hit_ratio": cache_efficiency["cache_hit_ratio"],
                    "semantic_hit_rate": cache_efficiency["semantic_hit_rate"],
                    "exact_hit_rate": cache_efficiency["exact_hit_rate"]
                },
                "token_efficiency": {
                    "big_model_tokens": current_stats["total_tokens_big"],
                    "small_model_tokens": current_stats["total_tokens_small"],
                    "tokens_saved": current_stats["total_tokens_saved"],
                    "tokens_saved_ratio": cache_efficiency["tokens_saved_ratio"],
                    "avg_tokens_per_request": cache_efficiency["avg_tokens_per_request"]
                },
                "performance": {
                    "avg_latency_ms": current_stats["avg_latency_ms"],
                    "p95_latency_ms": current_stats["latency_p95"],
                    "p99_latency_ms": current_stats["latency_p99"],
                    "uptime_seconds": current_stats["uptime_seconds"]
                },
                "recent_errors": current_stats["recent_errors"]
            }
        }
    
    def reset_metrics(self):
        """Reset all metrics (for testing or admin purposes)."""
        with self.lock:
            self.rolling_metrics = RollingMetrics()
            self.start_time = time.time()
            
            self.total_requests = 0
            self.exact_cache_hits = 0
            self.semantic_cache_hits = 0
            self.cache_misses = 0
            
            self.total_tokens_big = 0
            self.total_tokens_small = 0
            self.total_tokens_saved = 0
            
            self.total_latency_ms = 0
            self.latency_samples.clear()
            
            self.model_usage.clear()
            self.errors.clear()
            
            logger.info("Metrics reset")


# Global metrics instance
metrics = MetricsCollector()



