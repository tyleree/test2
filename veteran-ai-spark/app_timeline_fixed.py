import os
import json
import logging
from flask import Flask, request, jsonify, send_from_directory, send_file

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Enable CORS for all routes
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Admin-Token')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Resolve SPA dist folder regardless of working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR_CANDIDATES = [
    os.path.join(BASE_DIR, 'veteran-ai-spark', 'dist'),  # when running from repo root
    os.path.join(BASE_DIR, 'dist'),                      # when dist sits next to app.py
]
DIST_DIR = next((p for p in DIST_DIR_CANDIDATES if os.path.exists(os.path.join(p, 'index.html'))), None)

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    logger.info("Health check requested")
    return {"ok": True, "status": "running", "dist_dir": DIST_DIR}

@app.route("/ask", methods=["POST"])
def ask():
    """Ask a question and get an answer - simplified version for testing"""
    try:
        logger.info("Ask endpoint called")
        body = request.get_json(force=True)
        question = body.get('question', '')
        
        # Mock response for testing
        response = {
            "answer": f"This is a mock response to: {question}",
            "citations": [
                {"source_url": "https://example.com/doc1", "title": "Example Document 1"},
                {"source_url": "https://example.com/doc2", "title": "Example Document 2"}
            ],
            "latency_ms": 150,
            "token_usage": {
                "total_tokens": 500,
                "model_big": "gpt-4o",
                "model_small": "gpt-4o-mini"
            }
        }
        
        logger.info(f"Mock response for question: {question[:50]}...")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in ask endpoint: {str(e)}")
        return {"error": str(e)}, 500

@app.route("/api/analytics/stats", methods=["GET", "OPTIONS"])
def analytics_stats():
    """Mock analytics stats - completely open for debugging"""
    logger.info("=== ANALYTICS STATS REQUEST ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"URL: {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Args: {dict(request.args)}")
    logger.info(f"Remote addr: {request.remote_addr}")
    logger.info(f"================================")
    
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        # Mock data matching AdminAnalytics.tsx expectations
        analytics_data = {
            "totals": {
                "pageviews": 1500, "uniques": 450,
                "chat_questions": 25,
                "ask_count": 25,
                "visit_count": 450, "unique_visitors": 300
            },
            "by_day": [
                {"day": "2024-08-27", "pageviews": 200, "chat_questions": 15, "uniques": 45},
                {"day": "2024-08-26", "pageviews": 180, "chat_questions": 12, "uniques": 38},
                {"day": "2024-08-25", "pageviews": 220, "chat_questions": 18, "uniques": 52}
            ],
            "top_pages": [{"path": "/", "pageviews": 800}, {"path": "/stats", "pageviews": 300}, {"path": "/chat", "pageviews": 250}],
            "top_referrers": [{"referrer": "Direct", "visits": 200}, {"referrer": "Google", "visits": 150}, {"referrer": "GitHub", "visits": 75}],
            "visitor_locations": {
                "us_states": {"California": 45, "Texas": 32, "New York": 28},
                "international": 85, "local": 200, "unknown": 60, "total_tracked": 450,
                "raw_data": {"US": 305, "CA": 25, "UK": 20, "DE": 15}
            },
            "service_info": {
                "first_visit": "2024-08-01T00:00:00Z", "last_updated": "2024-08-27T16:00:00Z",
                "engagement_rate": 0.65, "questions_per_user": 2.3
            },
            "token_usage": {
                "total_tokens": 12500,
                "cache_hit_ratio": 0.75,
                "tokens_saved": 8200,
                "exact_hits": 15,
                "semantic_hits": 8,
                "cache_misses": 12
            },
            "performance": {
                "available": True,
                "summary": {
                    "total_chats": 35,
                    "avg_ms": 180,
                    "p95_ms": 350,
                    "success_rate": 0.97,
                    "avg_answer_chars": 850
                }
            }
        }
        logger.info("Returning analytics data successfully")
        return jsonify(analytics_data)
    except Exception as e:
        logger.error(f"Analytics stats error: {str(e)}")
        return {"error": str(e)}, 500

@app.route("/api/analytics/timeline", methods=["GET", "OPTIONS"])
def analytics_timeline():
    """Timeline data showing individual chat questions with token usage and cache info"""
    logger.info("=== TIMELINE REQUEST ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"URL: {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Args: {dict(request.args)}")
    logger.info(f"Remote addr: {request.remote_addr}")
    logger.info(f"========================")
    
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        # Mock timeline entries - individual chat questions with detailed info
        mock_entries = [
            {
                "id": 1,
                "timestamp": "2024-08-28T01:30:00Z",
                "question": "What benefits are available for veterans with PTSD?",
                "question_hash": "abc123def456",
                "cache_mode": "exact_hit",
                "semantic_similarity": 1.0,
                "answer_preview": "Veterans with PTSD are eligible for disability compensation, healthcare services, counseling...",
                "citations_count": 4,
                "token_usage": {
                    "model_big": "gpt-4o",
                    "model_small": "gpt-4o-mini", 
                    "tokens_big": 420,
                    "tokens_small": 0,
                    "total_tokens": 420
                },
                "latency_ms": 120,
                "retrieved_docs": 8,
                "compressed_tokens": 0,
                "final_tokens": 420,
                "user_ip": "10.229.217.199",
                "error_message": "",
                "created_at": "2024-08-28T01:30:00Z"
            },
            {
                "id": 2,
                "timestamp": "2024-08-28T01:25:00Z",
                "question": "How do I apply for VA disability benefits online?",
                "question_hash": "def456ghi789",
                "cache_mode": "semantic_hit",
                "semantic_similarity": 0.94,
                "answer_preview": "To apply for VA disability benefits online, visit eBenefits or VA.gov and complete Form 21-526EZ...",
                "citations_count": 3,
                "token_usage": {
                    "model_big": "gpt-4o",
                    "model_small": "gpt-4o-mini",
                    "tokens_big": 380,
                    "tokens_small": 150,
                    "total_tokens": 530
                },
                "latency_ms": 95,
                "retrieved_docs": 12,
                "compressed_tokens": 150,
                "final_tokens": 380,
                "user_ip": "10.229.201.132",
                "error_message": "",
                "created_at": "2024-08-28T01:25:00Z"
            },
            {
                "id": 3,
                "timestamp": "2024-08-28T01:20:00Z",
                "question": "What is the GI Bill and how much does it cover?",
                "question_hash": "ghi789jkl012",
                "cache_mode": "miss",
                "semantic_similarity": None,
                "answer_preview": "The GI Bill provides education benefits including tuition, housing allowance, and book stipends...",
                "citations_count": 5,
                "token_usage": {
                    "model_big": "gpt-4o",
                    "model_small": "gpt-4o-mini",
                    "tokens_big": 620,
                    "tokens_small": 280,
                    "total_tokens": 900
                },
                "latency_ms": 280,
                "retrieved_docs": 15,
                "compressed_tokens": 280,
                "final_tokens": 620,
                "user_ip": "10.229.31.196",
                "error_message": "",
                "created_at": "2024-08-28T01:20:00Z"
            },
            {
                "id": 4,
                "timestamp": "2024-08-28T01:15:00Z",
                "question": "Can I get VA healthcare if I'm not service-connected?",
                "question_hash": "jkl012mno345",
                "cache_mode": "miss",
                "semantic_similarity": None,
                "answer_preview": "Yes, veterans may be eligible for VA healthcare based on enrollment priority groups, even without service-connected disabilities...",
                "citations_count": 3,
                "token_usage": {
                    "model_big": "gpt-4o",
                    "model_small": "gpt-4o-mini",
                    "tokens_big": 480,
                    "tokens_small": 220,
                    "total_tokens": 700
                },
                "latency_ms": 195,
                "retrieved_docs": 10,
                "compressed_tokens": 220,
                "final_tokens": 480,
                "user_ip": "10.229.227.70",
                "error_message": "",
                "created_at": "2024-08-28T01:15:00Z"
            },
            {
                "id": 5,
                "timestamp": "2024-08-28T01:10:00Z",
                "question": "How long does it take to get a VA disability rating decision?",
                "question_hash": "mno345pqr678",
                "cache_mode": "semantic_hit",
                "semantic_similarity": 0.89,
                "answer_preview": "VA disability rating decisions typically take 3-4 months, but can vary based on complexity and evidence needed...",
                "citations_count": 2,
                "token_usage": {
                    "model_big": "gpt-4o",
                    "model_small": "gpt-4o-mini",
                    "tokens_big": 350,
                    "tokens_small": 120,
                    "total_tokens": 470
                },
                "latency_ms": 85,
                "retrieved_docs": 6,
                "compressed_tokens": 120,
                "final_tokens": 350,
                "user_ip": "10.229.220.131",
                "error_message": "",
                "created_at": "2024-08-28T01:10:00Z"
            },
            {
                "id": 6,
                "timestamp": "2024-08-28T01:05:00Z",
                "question": "What is the difference between VA disability and Social Security disability?",
                "question_hash": "pqr678stu901",
                "cache_mode": "exact_hit",
                "semantic_similarity": 1.0,
                "answer_preview": "VA disability and Social Security disability are separate programs with different eligibility criteria...",
                "citations_count": 3,
                "token_usage": {
                    "model_big": "gpt-4o",
                    "model_small": "gpt-4o-mini",
                    "tokens_big": 0,
                    "tokens_small": 0,
                    "total_tokens": 0
                },
                "latency_ms": 45,
                "retrieved_docs": 0,
                "compressed_tokens": 0,
                "final_tokens": 0,
                "user_ip": "10.229.217.199",
                "error_message": "",
                "created_at": "2024-08-28T01:05:00Z"
            }
        ]

        # Filter by cache_mode if specified
        cache_mode_filter = request.args.get('cache_mode')
        if cache_mode_filter and cache_mode_filter != 'all':
            mock_entries = [e for e in mock_entries if e['cache_mode'] == cache_mode_filter]

        # Timeline data in the format expected by AdminAnalytics component
        timeline_data = {
            "status": "ok",
            "entries": mock_entries,
            "stats": {
                "total_questions": len(mock_entries),
                "exact_hits": len([e for e in mock_entries if e["cache_mode"] == "exact_hit"]),
                "semantic_hits": len([e for e in mock_entries if e["cache_mode"] == "semantic_hit"]), 
                "cache_misses": len([e for e in mock_entries if e["cache_mode"] == "miss"]),
                "cache_hit_rate": 0.67,  # 4 hits out of 6 questions
                "avg_latency": sum(e["latency_ms"] for e in mock_entries) / len(mock_entries) if mock_entries else 0,
                "total_tokens_used": sum(e["token_usage"]["total_tokens"] for e in mock_entries),
                "avg_similarity": 0.943,  # Average of non-null similarities
                "hourly_breakdown": [
                    {"hour": "01:00", "questions": 6, "hits": 4},
                    {"hour": "00:00", "questions": 2, "hits": 1}
                ]
            },
            "pagination": {
                "limit": int(request.args.get('limit', 50)),
                "offset": int(request.args.get('offset', 0)),
                "total_returned": len(mock_entries)
            }
        }
        
        logger.info(f"Returning timeline data with {len(mock_entries)} entries")
        return jsonify(timeline_data)
    except Exception as e:
        logger.error(f"Timeline error: {str(e)}")
        return {"error": str(e)}, 500

# Serve React SPA
@app.route('/')
def serve_spa():
    """Serve the React SPA."""
    logger.info(f"Serving SPA from: {DIST_DIR}")
    if not DIST_DIR:
        return "SPA not built. Run 'npm run build' in veteran-ai-spark/ first.", 404
    return send_file(os.path.join(DIST_DIR, 'index.html'))

@app.route('/admin/analytics')
def admin_analytics():
    """Serve the admin analytics page."""
    logger.info(f"Serving admin analytics from: {DIST_DIR}")
    if not DIST_DIR:
        return "SPA not built. Run 'npm run build' in veteran-ai-spark/ first.", 404
    return send_file(os.path.join(DIST_DIR, 'index.html'))

@app.route('/analytics')
def analytics_page():
    """Handle legacy analytics route."""
    logger.info(f"Serving analytics page from: {DIST_DIR}")
    if not DIST_DIR:
        return "SPA not built. Run 'npm run build' in veteran-ai-spark/ first.", 404
    return send_file(os.path.join(DIST_DIR, 'index.html'))

# Static assets and catch-all for SPA routing (must be last)
@app.route('/<path:path>')
def serve_spa_assets(path):
    """Serve SPA static assets."""
    logger.info(f"Serving asset: {path} from {DIST_DIR}")
    # Skip API routes
    if path.startswith('api/'):
        return "API endpoint not found", 404
    if not DIST_DIR:
        return "SPA not built. Run 'npm run build' in veteran-ai-spark/ first.", 404
    try:
        # First try to serve from resolved dist directory
        return send_from_directory(DIST_DIR, path)
    except FileNotFoundError:
        # If not found, serve the SPA (for client-side routing)
        return send_file(os.path.join(DIST_DIR, 'index.html'))

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask TIMELINE FIXED VERSION on port {port}")
    print(f"DIST_DIR resolved to: {DIST_DIR}")
    print("*** TIMELINE NOW SHOWS INDIVIDUAL CHAT QUESTIONS WITH DETAILED TOKEN & CACHE INFO ***")
    app.run(host='0.0.0.0', port=port, debug=True)
