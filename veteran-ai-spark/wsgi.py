"""
WSGI entry point for production deployment.
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from app.factory import create_app
    # Create application instance
    app = create_app()
except ImportError:
    # Fallback to simple Flask app if factory is not available
    from flask import Flask, request, jsonify
    app = Flask(__name__)

# Add whitepaper route directly to ensure it's available
@app.route('/api/whitepaper', methods=['GET'])
def whitepaper():
    """Serve the technical whitepaper."""
    try:
        from flask import request
        
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
        import logging
        logging.error(f"Error serving whitepaper: {e}")
        return jsonify({'error': 'Failed to load whitepaper'}), 500

if __name__ == "__main__":
    # For development
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    
    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug
    )
