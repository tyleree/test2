"""
Comprehensive metrics tracking and logging for RAG pipeline.
Tracks token usage, cache performance, latency, and quality metrics.
"""

import logging
import json
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

@dataclass
class RequestMetrics:
    """Metrics for a single request."""
    timestamp: str
    query: str
    cache_mode: str  # 'exact', 'semantic', 'miss'
    latency_ms: int
    tokens_small_in: int
    tokens_small_out: int
    tokens_big_in: int
    tokens_big_out: int
    retrieved: int
    reranked: int
    quotes: int
    saved_tokens_estimate: int
    status: str
    error_message: Optional[str] = None

@dataclass
class AggregateMetrics:
    """Aggregate metrics over time window."""
    total_requests: int
    cache_hit_rate: float
    avg_latency_ms: float
    total_tokens_used: int
    total_tokens_saved: int
    avg_retrieved: float
    avg_reranked: float
    avg_quotes: float
    success_rate: float

class MetricsTracker:
    """Tracks and aggregates RAG pipeline metrics."""
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.request_history: deque = deque(maxlen=window_size)
        self.hourly_stats: Dict[str, Dict] = defaultdict(dict)
        
        # Real-time counters
        self.total_requests = 0
        self.cache_hits = 0
        self.total_latency = 0
        self.total_tokens_used = 0
        self.total_tokens_saved = 0
        self.errors = 0
    
    def log_request(self, metrics: RequestMetrics) -> None:
        """Log metrics for a single request."""
        try:
            # Add to history
            self.request_history.append(metrics)
            
            # Update counters
            self.total_requests += 1
            if metrics.cache_mode in ['exact', 'semantic']:
                self.cache_hits += 1
            
            self.total_latency += metrics.latency_ms
            
            tokens_used = (metrics.tokens_small_in + metrics.tokens_small_out + 
                          metrics.tokens_big_in + metrics.tokens_big_out)
            self.total_tokens_used += tokens_used
            self.total_tokens_saved += metrics.saved_tokens_estimate
            
            if metrics.status == 'error':
                self.errors += 1
            
            # Update hourly stats
            hour_key = datetime.fromisoformat(metrics.timestamp.replace('Z', '+00:00')).strftime('%Y-%m-%d-%H')
            if hour_key not in self.hourly_stats:
                self.hourly_stats[hour_key] = {
                    'requests': 0,
                    'cache_hits': 0,
                    'total_latency': 0,
                    'total_tokens': 0,
                    'errors': 0
                }
            
            hour_stats = self.hourly_stats[hour_key]
            hour_stats['requests'] += 1
            if metrics.cache_mode in ['exact', 'semantic']:
                hour_stats['cache_hits'] += 1
            hour_stats['total_latency'] += metrics.latency_ms
            hour_stats['total_tokens'] += tokens_used
            if metrics.status == 'error':
                hour_stats['errors'] += 1
            
            # Log JSON for external processing
            self._log_json_metrics(metrics)
            
        except Exception as e:
            logger.error(f"Failed to log metrics: {e}")
    
    def _log_json_metrics(self, metrics: RequestMetrics) -> None:
        """Log metrics as JSON for external processing."""
        try:
            # Create clean metrics dict for JSON logging
            metrics_dict = asdict(metrics)
            
            # Truncate query for logging
            if len(metrics_dict['query']) > 100:
                metrics_dict['query'] = metrics_dict['query'][:100] + "..."
            
            logger.info(f"METRICS: {json.dumps(metrics_dict)}")
            
        except Exception as e:
            logger.warning(f"Failed to log JSON metrics: {e}")
    
    def get_current_stats(self) -> AggregateMetrics:
        """Get current aggregate statistics."""
        if self.total_requests == 0:
            return AggregateMetrics(
                total_requests=0,
                cache_hit_rate=0.0,
                avg_latency_ms=0.0,
                total_tokens_used=0,
                total_tokens_saved=0,
                avg_retrieved=0.0,
                avg_reranked=0.0,
                avg_quotes=0.0,
                success_rate=0.0
            )
        
        # Calculate averages from recent requests
        recent_requests = list(self.request_history)
        
        if recent_requests:
            avg_latency = sum(r.latency_ms for r in recent_requests) / len(recent_requests)
            avg_retrieved = sum(r.retrieved for r in recent_requests) / len(recent_requests)
            avg_reranked = sum(r.reranked for r in recent_requests) / len(recent_requests)
            avg_quotes = sum(r.quotes for r in recent_requests) / len(recent_requests)
            success_count = sum(1 for r in recent_requests if r.status == 'success')
            success_rate = success_count / len(recent_requests)
        else:
            avg_latency = self.total_latency / self.total_requests
            avg_retrieved = 0.0
            avg_reranked = 0.0
            avg_quotes = 0.0
            success_rate = 1.0 - (self.errors / self.total_requests)
        
        return AggregateMetrics(
            total_requests=self.total_requests,
            cache_hit_rate=self.cache_hits / self.total_requests,
            avg_latency_ms=avg_latency,
            total_tokens_used=self.total_tokens_used,
            total_tokens_saved=self.total_tokens_saved,
            avg_retrieved=avg_retrieved,
            avg_reranked=avg_reranked,
            avg_quotes=avg_quotes,
            success_rate=success_rate
        )
    
    def get_hourly_breakdown(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get hourly metrics breakdown."""
        breakdown = []
        
        # Get last N hours
        current_time = datetime.utcnow()
        for i in range(hours):
            hour_time = current_time - timedelta(hours=i)
            hour_key = hour_time.strftime('%Y-%m-%d-%H')
            
            stats = self.hourly_stats.get(hour_key, {
                'requests': 0,
                'cache_hits': 0,
                'total_latency': 0,
                'total_tokens': 0,
                'errors': 0
            })
            
            # Calculate rates
            cache_hit_rate = stats['cache_hits'] / stats['requests'] if stats['requests'] > 0 else 0
            avg_latency = stats['total_latency'] / stats['requests'] if stats['requests'] > 0 else 0
            error_rate = stats['errors'] / stats['requests'] if stats['requests'] > 0 else 0
            
            breakdown.append({
                'hour': hour_key,
                'timestamp': hour_time.isoformat() + 'Z',
                'requests': stats['requests'],
                'cache_hit_rate': round(cache_hit_rate, 3),
                'avg_latency_ms': round(avg_latency, 1),
                'total_tokens': stats['total_tokens'],
                'error_rate': round(error_rate, 3)
            })
        
        return list(reversed(breakdown))  # Most recent first
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        current_stats = self.get_current_stats()
        
        # Token efficiency
        token_efficiency = 0.0
        if self.total_tokens_used > 0:
            token_efficiency = self.total_tokens_saved / (self.total_tokens_used + self.total_tokens_saved)
        
        # Recent performance (last 100 requests)
        recent_requests = list(self.request_history)[-100:]
        recent_cache_hits = sum(1 for r in recent_requests if r.cache_mode in ['exact', 'semantic'])
        recent_cache_rate = recent_cache_hits / len(recent_requests) if recent_requests else 0
        
        # Latency percentiles
        latencies = [r.latency_ms for r in recent_requests] if recent_requests else [0]
        latencies.sort()
        
        p50_latency = latencies[len(latencies) // 2] if latencies else 0
        p95_latency = latencies[int(len(latencies) * 0.95)] if latencies else 0
        p99_latency = latencies[int(len(latencies) * 0.99)] if latencies else 0
        
        return {
            'overview': asdict(current_stats),
            'efficiency': {
                'token_efficiency': round(token_efficiency, 3),
                'recent_cache_rate': round(recent_cache_rate, 3),
                'cost_savings_estimate': self.total_tokens_saved * 0.00002  # Rough cost per token
            },
            'latency': {
                'p50_ms': p50_latency,
                'p95_ms': p95_latency,
                'p99_ms': p99_latency,
                'avg_ms': round(current_stats.avg_latency_ms, 1)
            },
            'quality': {
                'success_rate': round(current_stats.success_rate, 3),
                'avg_quotes_per_answer': round(current_stats.avg_quotes, 1),
                'avg_sources_retrieved': round(current_stats.avg_retrieved, 1),
                'avg_sources_reranked': round(current_stats.avg_reranked, 1)
            }
        }
    
    def reset_stats(self) -> None:
        """Reset all statistics."""
        self.request_history.clear()
        self.hourly_stats.clear()
        self.total_requests = 0
        self.cache_hits = 0
        self.total_latency = 0
        self.total_tokens_used = 0
        self.total_tokens_saved = 0
        self.errors = 0
        
        logger.info("Metrics statistics reset")

# Global metrics tracker instance
metrics_tracker = MetricsTracker()

def log_request_metrics(
    query: str,
    cache_mode: str,
    latency_ms: int,
    tokens_small_in: int = 0,
    tokens_small_out: int = 0,
    tokens_big_in: int = 0,
    tokens_big_out: int = 0,
    retrieved: int = 0,
    reranked: int = 0,
    quotes: int = 0,
    saved_tokens_estimate: int = 0,
    status: str = 'success',
    error_message: Optional[str] = None
) -> None:
    """Convenience function to log request metrics."""
    
    metrics = RequestMetrics(
        timestamp=datetime.utcnow().isoformat() + 'Z',
        query=query,
        cache_mode=cache_mode,
        latency_ms=latency_ms,
        tokens_small_in=tokens_small_in,
        tokens_small_out=tokens_small_out,
        tokens_big_in=tokens_big_in,
        tokens_big_out=tokens_big_out,
        retrieved=retrieved,
        reranked=reranked,
        quotes=quotes,
        saved_tokens_estimate=saved_tokens_estimate,
        status=status,
        error_message=error_message
    )
    
    metrics_tracker.log_request(metrics)