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
from guard import CFG, select_and_gate, SYSTEM_GUARDED, build_user_prompt

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
        
        # Build guard hits from reranked candidates
        raw_hits = [
            {
                'text': rc.text,
                'rel': float(getattr(rc, 'rel', 0.0)),
                'cross': float(getattr(rc, 'cross', 0.0)),
                'meta': {'url': rc.source_url}
            }
            for rc in reranked_candidates
        ]

        selected_hits, agg_conf = select_and_gate(raw_hits)

        # If insufficient context, short-circuit with safe message
        if (not selected_hits) or (agg_conf < CFG.MIN_CONF):
            latency_ms = int((time.time() - start_time) * 1000)
            log_request_metrics(
                query=query,
                cache_mode=cache_mode,
                latency_ms=latency_ms,
                retrieved=len(candidates),
                reranked=len(reranked_candidates),
                quotes=0,
                status='insufficient_context'
            )
            return jsonify({
                'status': 'insufficient_context',
                'agg_conf': round(agg_conf, 3),
                'message': CFG.SAFE_MSG,
                'cache_mode': cache_mode,
                'token_usage': {},
                'latency_ms': latency_ms
            }), 200

        # Compression (use only selected hits' texts as quotes input)
        # Map selected hits back to reranked candidates preserving URL and titles
        filtered_candidates = []
        selected_texts = {h['text'] for h in selected_hits}
        for rc in reranked_candidates:
            if rc.text in selected_texts:
                filtered_candidates.append(rc)

        compression_result = compressor.compress(query, filtered_candidates)
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
        
        # Build guard evidence array (top selected with scores if available)
        evidence = []
        try:
            # selected_hits and agg_conf exist if we didn't early return
            evidence = [
                {
                    'sid': h.get('sid'),
                    'url': h.get('meta', {}).get('url'),
                    'rel': round(float(h.get('rel', 0.0)), 3),
                    'cross': round(float(h.get('cross', 0.0)), 3),
                    'final': round(float(h.get('final', 0.0)), 3)
                }
                for h in (selected_hits if 'selected_hits' in locals() else [])
            ]
        except Exception:
            evidence = []

        return jsonify({
            'status': 'ok',
            'agg_conf': round(agg_conf, 3) if 'agg_conf' in locals() else None,
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
            'evidence': evidence,
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

@api.route('/whitepaper', methods=['GET'])
def whitepaper():
    """Serve the technical whitepaper."""
    try:
        import markdown
        import os
        from flask import request
        
        # Check if LaTeX version is requested
        format_type = request.args.get('format', 'html')
        
        if format_type == 'latex':
            # Serve LaTeX source
            latex_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'whitepaper.tex')
            if not os.path.exists(latex_path):
                return jsonify({'error': 'LaTeX whitepaper not found'}), 404
            
            with open(latex_path, 'r', encoding='utf-8') as f:
                latex_content = f.read()
            
            return latex_content, 200, {
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Disposition': 'attachment; filename="veteran-ai-spark-whitepaper.tex"'
            }
        
        # Default: serve HTML version
        # Read the whitepaper markdown file
        whitepaper_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'whitepaper.md')
        
        if not os.path.exists(whitepaper_path):
            return jsonify({'error': 'Whitepaper not found'}), 404
        
        with open(whitepaper_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # Convert markdown to HTML
        html_content = markdown.markdown(
            markdown_content,
            extensions=['tables', 'fenced_code', 'toc', 'codehilite'],
            extension_configs={
                'toc': {'title': 'Table of Contents'},
                'codehilite': {'use_pygments': False}
            }
        )
        
        # Create a complete HTML page
        html_page = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Technical Whitepaper - Veteran AI Spark RAG System</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #fafafa;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #1a365d;
            border-bottom: 3px solid #3182ce;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #2d3748;
            margin-top: 2em;
            border-left: 4px solid #3182ce;
            padding-left: 15px;
        }}
        h3 {{
            color: #4a5568;
            margin-top: 1.5em;
        }}
        code {{
            background-color: #f7fafc;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.9em;
        }}
        pre {{
            background-color: #f7fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 15px;
            overflow-x: auto;
            margin: 1em 0;
        }}
        pre code {{
            background: none;
            padding: 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }}
        th, td {{
            border: 1px solid #e2e8f0;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background-color: #f7fafc;
            font-weight: 600;
        }}
        .toc {{
            background-color: #f7fafc;
            border: 1px solid #e2e8f0;
            border-radius: 6px;
            padding: 20px;
            margin: 20px 0;
        }}
        .toc ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .math {{
            font-family: 'Times New Roman', serif;
            font-style: italic;
        }}
        .highlight {{
            background-color: #fff3cd;
            padding: 15px;
            border-left: 4px solid #ffc107;
            margin: 1em 0;
        }}
        .nav-header {{
            background: #1a365d;
            color: white;
            padding: 15px 40px;
            margin: -40px -40px 40px -40px;
            border-radius: 8px 8px 0 0;
        }}
        .nav-header h1 {{
            margin: 0;
            color: white;
            border: none;
            padding: 0;
        }}
        .back-link {{
            display: inline-block;
            margin-top: 15px;
            color: #3182ce;
            text-decoration: none;
            font-weight: 500;
        }}
        .back-link:hover {{
            text-decoration: underline;
        }}
        @media (max-width: 768px) {{
            body {{
                padding: 10px;
            }}
            .container {{
                padding: 20px;
            }}
            .nav-header {{
                padding: 15px 20px;
                margin: -20px -20px 20px -20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="nav-header">
            <h1>Technical Whitepaper</h1>
            <p style="margin: 0; opacity: 0.9;">Veteran AI Spark RAG System - Comprehensive Technical Documentation</p>
        </div>
        
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <a href="/" class="back-link">← Back to Main Site</a>
            <a href="/api/whitepaper?format=latex" class="back-link" download="veteran-ai-spark-whitepaper.tex">
                📄 Download LaTeX Source
            </a>
        </div>
        
        {html_content}
        
        <hr style="margin: 40px 0; border: none; border-top: 1px solid #e2e8f0;">
        <div style="text-align: center; color: #718096; font-size: 0.9em;">
            <a href="/" class="back-link">← Return to Veteran AI Spark</a>
            <span style="margin: 0 20px;">|</span>
            <a href="/api/whitepaper?format=latex" class="back-link" download="veteran-ai-spark-whitepaper.tex">
                📄 Download LaTeX Source
            </a>
        </div>
    </div>
</body>
</html>
        """
        
        return html_page, 200, {'Content-Type': 'text/html'}
        
    except ImportError:
        # Fallback if markdown is not installed
        return jsonify({
            'error': 'Markdown processor not available',
            'message': 'Please install python-markdown to view the whitepaper'
        }), 500
    except Exception as e:
        logger.error(f"Error serving whitepaper: {e}")
        return jsonify({'error': 'Failed to load whitepaper'}), 500

@api.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500
