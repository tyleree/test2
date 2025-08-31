"""
Flask routes for the RAG API including debug endpoints.
"""

import logging
import time
from typing import Dict, Any, Optional
import traceback

from flask import Blueprint, request, jsonify, current_app
from werkzeug.exceptions import BadRequest

from .config import config
from .retrieval import HybridRetriever
from .rerank import CrossEncoderReranker
from .compress import QuoteCompressor
from .answer import AnswerGenerator
from .cache import SemanticCache
from .metrics import log_request_metrics, metrics_tracker
from .utils import normalize_query, get_token_count

logger = logging.getLogger(__name__)

# Create Blueprint
api = Blueprint('api', __name__)

# Global instances (will be initialized by factory)
retriever: Optional[HybridRetriever] = None
reranker: Optional[CrossEncoderReranker] = None
compressor: Optional[QuoteCompressor] = None
answer_generator: Optional[AnswerGenerator] = None
semantic_cache: Optional[SemanticCache] = None

# Debug storage for last operations
debug_state = {
    'last_retrieval': None,
    'last_rerank': None,
    'last_quotes': None,
    'last_cache_decision': None
}

def init_components():
    """Initialize RAG pipeline components."""
    global retriever, reranker, compressor, answer_generator, semantic_cache
    
    try:
        logger.info("Initializing RAG pipeline components...")
        
        retriever = HybridRetriever()
        reranker = CrossEncoderReranker()
        compressor = QuoteCompressor()
        answer_generator = AnswerGenerator()
        semantic_cache = SemanticCache()
        
        logger.info("RAG pipeline components initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize RAG components: {e}")
        raise

@api.route('/ask', methods=['POST'])
def ask():
    """Main RAG endpoint."""
    start_time = time.time()
    
    try:
        # Validate request
        if not request.is_json:
            raise BadRequest("Request must be JSON")
        
        data = request.get_json()
        if not data or 'question' not in data:
            raise BadRequest("Missing 'question' field")
        
        query = data['question'].strip()
        if not query:
            raise BadRequest("Question cannot be empty")
        
        logger.info(f"Processing query: '{query[:100]}...'")
        
        # Initialize components if needed
        if not all([retriever, reranker, compressor, answer_generator, semantic_cache]):
            init_components()
        
        # Step 1: Check cache first
        cache_hit = None
        cache_mode = 'miss'
        
        try:
            # Do a quick retrieval to get current doc IDs for cache validation
            quick_candidates = retriever.retrieve(query)[:10]  # Just top 10 for validation
            current_doc_ids = [c.doc_id for c in quick_candidates]
            
            cache_hit = semantic_cache.retrieve(query, current_doc_ids)
            if cache_hit:
                cache_mode = cache_hit.hit_type
                
                # Return cached result
                latency_ms = int((time.time() - start_time) * 1000)
                
                log_request_metrics(
                    query=query,
                    cache_mode=cache_mode,
                    latency_ms=latency_ms,
                    saved_tokens_estimate=sum(cache_hit.entry.token_usage.values()),
                    status='success'
                )
                
                # Update debug state
                debug_state['last_cache_decision'] = {
                    'hit': True,
                    'type': cache_hit.hit_type,
                    'similarity': cache_hit.similarity,
                    'cached_query': cache_hit.entry.normalized_query
                }
                
                return jsonify({
                    'answer_plain': cache_hit.entry.answer_result.answer_plain,
                    'answer_html': cache_hit.entry.answer_result.answer_html,
                    'citations': [
                        {
                            'n': citation.n,
                            'url': citation.url,
                            'title': citation.title
                        }
                        for citation in cache_hit.entry.answer_result.citations
                    ],
                    'cache_mode': cache_mode,
                    'token_usage': cache_hit.entry.token_usage,
                    'latency_ms': latency_ms
                })
        
        except Exception as e:
            logger.warning(f"Cache check failed: {e}, proceeding with full pipeline")
        
        # Step 2: Full RAG pipeline
        
        # Retrieval
        candidates = retriever.retrieve(query)
        debug_state['last_retrieval'] = {
            'candidates': len(candidates),
            'top_candidates': [
                {
                    'chunk_id': c.chunk_id,
                    'title': c.title,
                    'combined_score': c.combined_score,
                    'text_preview': c.text[:100] + "..." if len(c.text) > 100 else c.text
                }
                for c in candidates[:5]
            ]
        }
        
        if not candidates:
            latency_ms = int((time.time() - start_time) * 1000)
            
            log_request_metrics(
                query=query,
                cache_mode=cache_mode,
                latency_ms=latency_ms,
                retrieved=0,
                status='no_results'
            )
            
            return jsonify({
                'answer_plain': "I couldn't find any relevant information to answer your question.",
                'answer_html': "<p>I couldn't find any relevant information to answer your question.</p>",
                'citations': [],
                'cache_mode': cache_mode,
                'token_usage': {},
                'latency_ms': latency_ms
            })
        
        # Reranking
        reranked_candidates = reranker.rerank(query, candidates)
        debug_state['last_rerank'] = reranker.get_debug_info(reranked_candidates)
        
        # Compression
        compression_result = compressor.compress(query, reranked_candidates)
        debug_state['last_quotes'] = compressor.get_debug_info(compression_result)
        
        # Answer generation
        answer_result = answer_generator.generate_answer(query, compression_result)
        
        # Cache the result
        try:
            top_doc_ids = [c.doc_id for c in candidates[:20]]  # Cache top 20 doc IDs
            total_token_usage = {
                'compression_tokens': get_token_count(str(compression_result.quotes)),
                'answer_tokens': answer_result.token_usage.get('total_tokens', 0)
            }
            
            semantic_cache.store(query, top_doc_ids, answer_result, total_token_usage)
        except Exception as e:
            logger.warning(f"Failed to cache result: {e}")
        
        # Calculate final metrics
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Estimate token usage
        compression_tokens = get_token_count(str([q.text for q in compression_result.quotes]))
        
        log_request_metrics(
            query=query,
            cache_mode=cache_mode,
            latency_ms=latency_ms,
            tokens_small_in=compression_tokens,
            tokens_small_out=compression_result.total_tokens,
            tokens_big_in=answer_result.token_usage.get('prompt_tokens', 0),
            tokens_big_out=answer_result.token_usage.get('completion_tokens', 0),
            retrieved=len(candidates),
            reranked=len(reranked_candidates),
            quotes=len(compression_result.quotes),
            status='success' if answer_result.status == 'success' else 'partial'
        )
        
        # Update debug state
        debug_state['last_cache_decision'] = {
            'hit': False,
            'type': 'miss',
            'reason': 'No valid cache entry found'
        }
        
        return jsonify({
            'answer_plain': answer_result.answer_plain,
            'answer_html': answer_result.answer_html,
            'citations': [
                {
                    'n': citation.n,
                    'url': citation.url,
                    'title': citation.title
                }
                for citation in answer_result.citations
            ],
            'cache_mode': cache_mode,
            'token_usage': {
                'compression': compression_result.total_tokens,
                'answer': answer_result.token_usage.get('total_tokens', 0),
                'total': compression_result.total_tokens + answer_result.token_usage.get('total_tokens', 0)
            },
            'latency_ms': latency_ms
        })
    
    except BadRequest as e:
        latency_ms = int((time.time() - start_time) * 1000)
        log_request_metrics(
            query=data.get('question', '') if 'data' in locals() else '',
            cache_mode='error',
            latency_ms=latency_ms,
            status='error',
            error_message=str(e)
        )
        return jsonify({'error': str(e)}), 400
    
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Internal server error: {str(e)}"
        
        log_request_metrics(
            query=data.get('question', '') if 'data' in locals() else '',
            cache_mode='error',
            latency_ms=latency_ms,
            status='error',
            error_message=error_msg
        )
        
        logger.error(f"Error in /ask endpoint: {e}")
        logger.error(traceback.format_exc())
        
        return jsonify({'error': 'Internal server error'}), 500

@api.route('/debug/retrieval', methods=['GET'])
def debug_retrieval():
    """Get debug info about last retrieval."""
    return jsonify(debug_state.get('last_retrieval', {'message': 'No retrieval data available'}))

@api.route('/debug/rerank', methods=['GET'])
def debug_rerank():
    """Get debug info about last rerank."""
    return jsonify(debug_state.get('last_rerank', {'message': 'No rerank data available'}))

@api.route('/debug/quotes', methods=['GET'])
def debug_quotes():
    """Get debug info about last quote extraction."""
    return jsonify(debug_state.get('last_quotes', {'message': 'No quotes data available'}))

@api.route('/debug/cache', methods=['GET'])
def debug_cache():
    """Get debug info about last cache decision."""
    return jsonify(debug_state.get('last_cache_decision', {'message': 'No cache data available'}))

@api.route('/healthz', methods=['GET'])
def health_check():
    """Health check endpoint."""
    try:
        # Check if components are initialized
        components_status = {
            'retriever': retriever is not None,
            'reranker': reranker is not None,
            'compressor': compressor is not None,
            'answer_generator': answer_generator is not None,
            'semantic_cache': semantic_cache is not None
        }
        
        all_healthy = all(components_status.values())
        
        return jsonify({
            'status': 'healthy' if all_healthy else 'degraded',
            'components': components_status,
            'config': {
                'model_big': config.model_big,
                'model_small': config.model_small,
                'pinecone_index': config.pinecone_index,
                'cache_enabled': semantic_cache is not None
            }
        }), 200 if all_healthy else 503
    
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503

@api.route('/metrics', methods=['GET'])
def get_metrics():
    """Get performance metrics."""
    try:
        summary = metrics_tracker.get_performance_summary()
        hourly = metrics_tracker.get_hourly_breakdown()
        
        if semantic_cache:
            cache_stats = semantic_cache.get_stats()
        else:
            cache_stats = {'error': 'Cache not initialized'}
        
        return jsonify({
            'performance': summary,
            'hourly_breakdown': hourly,
            'cache_stats': cache_stats,
            'timestamp': time.time()
        })
    
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return jsonify({'error': str(e)}), 500

@api.route('/cache/stats', methods=['GET'])
def cache_stats():
    """Get cache statistics."""
    try:
        if not semantic_cache:
            return jsonify({'error': 'Cache not initialized'}), 503
        
        stats = semantic_cache.get_stats()
        return jsonify(stats)
    
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return jsonify({'error': str(e)}), 500

@api.route('/cache/clear', methods=['POST'])
def clear_cache():
    """Clear cache entries (requires admin token)."""
    try:
        # Simple token check (in production, use proper authentication)
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401
        
        token = auth_header.split(' ')[1]
        if token != 'admin-token':  # In production, use proper token validation
            return jsonify({'error': 'Invalid token'}), 401
        
        if not semantic_cache:
            return jsonify({'error': 'Cache not initialized'}), 503
        
        # Get request parameters
        data = request.get_json() or {}
        keep_current = data.get('keep_current_version', True)
        
        deleted_count = semantic_cache.clear_old_entries(keep_current)
        
        return jsonify({
            'message': f'Cleared {deleted_count} cache entries',
            'deleted_count': deleted_count,
            'kept_current_version': keep_current
        })
    
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return jsonify({'error': str(e)}), 500

@api.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({'error': 'Endpoint not found'}), 404

@api.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500
