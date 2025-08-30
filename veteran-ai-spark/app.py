#!/usr/bin/env python3
"""
Main Flask application entry point.
This file imports and runs the fixed Flask app.
"""

from app_fixed import app

if __name__ == "__main__":
    import os
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Flask on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
