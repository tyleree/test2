import os
import json
import logging
from flask import Flask, request, jsonify, send_from_directory, send_file

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

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
    return {"ok": True, "status": "running"}

@app.route("/ask", methods=["POST"])
def ask():
    """Ask a question and get an answer - simplified version for testing"""
    try:
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

@app.route("/api/analytics/stats", methods=["GET"])
def analytics_stats():
    """Mock analytics stats for testing"""
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
        return jsonify(analytics_data)
    except Exception as e:
        logger.error(f"Analytics stats error: {str(e)}")
        return {"error": str(e)}, 500

@app.route("/api/analytics/timeline", methods=["GET"])
def analytics_timeline():
    """Mock timeline data for testing"""
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
        return jsonify(timeline_data)
    except Exception as e:
        logger.error(f"Timeline error: {str(e)}")
        return {"error": str(e)}, 500

@app.route("/api/test", methods=["GET"])
def test_route():
    """Test route to verify deployment."""
    return jsonify({"message": "Test route working", "timestamp": "2024-12-19"})

@app.route("/api/whitepaper", methods=["GET"])
def whitepaper():
    """Serve the technical whitepaper."""
    try:
        # Check if LaTeX version is requested
        format_type = request.args.get('format', 'html')
        
        if format_type == 'latex':
            # Serve LaTeX source
            latex_path = os.path.join(os.path.dirname(__file__), 'whitepaper.tex')
            if not os.path.exists(latex_path):
                return jsonify({'error': 'LaTeX whitepaper not found'}), 404
            
            with open(latex_path, 'r', encoding='utf-8') as f:
                latex_content = f.read()
            
            return latex_content, 200, {
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Disposition': 'attachment; filename="veteran-ai-spark-whitepaper.tex"'
            }
        
        # Default: serve HTML version
        # Try to import markdown, fallback if not available
        try:
            import markdown
        except ImportError:
            return jsonify({
                'error': 'Markdown processor not available',
                'message': 'Please install python-markdown to view the whitepaper'
            }), 500
        
        # Read the whitepaper markdown file
        whitepaper_path = os.path.join(os.path.dirname(__file__), 'whitepaper.md')
        
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
        
    except Exception as e:
        logger.error(f"Error serving whitepaper: {e}")
        return jsonify({'error': 'Failed to load whitepaper'}), 500

# Serve React SPA
@app.route('/')
def serve_spa():
    """Serve the React SPA."""
    if not DIST_DIR:
        return "SPA not built. Run 'npm run build' in veteran-ai-spark/ first.", 404
    return send_file(os.path.join(DIST_DIR, 'index.html'))

@app.route('/admin/analytics')
def admin_analytics():
    """Serve the admin analytics page."""
    if not DIST_DIR:
        return "SPA not built. Run 'npm run build' in veteran-ai-spark/ first.", 404
    return send_file(os.path.join(DIST_DIR, 'index.html'))

@app.route('/analytics')
def analytics_page():
    """Handle legacy analytics route."""
    if not DIST_DIR:
        return "SPA not built. Run 'npm run build' in veteran-ai-spark/ first.", 404
    return send_file(os.path.join(DIST_DIR, 'index.html'))

# Static assets and catch-all for SPA routing (must be last)
@app.route('/<path:path>')
def serve_spa_assets(path):
    """Serve SPA static assets."""
    # Skip API routes - let them be handled by their specific routes
    if path.startswith('api/'):
        # If we get here, it means the API route doesn't exist
        return jsonify({"error": "API endpoint not found"}), 404
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
    print(f"Starting Flask on port {port}")
    print(f"DIST_DIR resolved to: {DIST_DIR}")
    app.run(host='0.0.0.0', port=port, debug=True)
