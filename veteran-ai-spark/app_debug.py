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
    """Mock timeline data - completely open for debugging"""
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
        # Mock timeline data
        timeline_data = [
            {
                "id": 1,
                "timestamp": "2024-08-27T16:30:00Z",
                "question": "What benefits are available for veterans?",
                "cache_mode": "exact_hit",
                "semantic_similarity": 1.0,
                "answer_preview": "Veterans are eligible for various benefits including healthcare, education, disability compensation...",
                "citations_count": 3,
                "token_usage": {"total_tokens": 450, "model_big": "gpt-4o"},
                "latency_ms": 120,
                "user_ip": "192.168.1.1"
            },
            {
                "id": 2,
                "timestamp": "2024-08-27T16:25:00Z",
                "question": "How do I apply for VA disability benefits?",
                "cache_mode": "semantic_hit",
                "semantic_similarity": 0.94,
                "answer_preview": "To apply for VA disability benefits, you can submit your application online...",
                "citations_count": 2,
                "token_usage": {"total_tokens": 380, "model_big": "gpt-4o"},
                "latency_ms": 95,
                "user_ip": "192.168.1.2"
            },
            {
                "id": 3,
                "timestamp": "2024-08-27T16:20:00Z",
                "question": "What is the GI Bill education benefit?",
                "cache_mode": "miss",
                "semantic_similarity": None,
                "answer_preview": "The GI Bill provides education benefits to eligible veterans and their families...",
                "citations_count": 4,
                "token_usage": {"total_tokens": 620, "model_big": "gpt-4o", "model_small": "gpt-4o-mini"},
                "latency_ms": 280,
                "user_ip": "192.168.1.3"
            }
        ]
        logger.info("Returning timeline data successfully")
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
    print(f"Starting Flask DEBUG VERSION on port {port}")
    print(f"DIST_DIR resolved to: {DIST_DIR}")
    print("*** THIS VERSION HAS NO AUTHENTICATION - FOR DEBUGGING ONLY ***")
    app.run(host='0.0.0.0', port=port, debug=True)
