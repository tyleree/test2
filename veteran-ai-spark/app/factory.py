"""
Flask application factory for the RAG backend.
"""

import logging
from flask import Flask
from flask_cors import CORS

from .config import config
from .routes import api, init_components

def create_app(config_override=None):
    """Create and configure Flask application."""
    
    # Create Flask app
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config)
    if config_override:
        app.config.update(config_override)
    
    # Set up CORS
    CORS(app, origins="*")  # Configure appropriately for production
    
    # Set up logging
    setup_logging(app)
    
    # Register blueprints
    app.register_blueprint(api, url_prefix='/api')
    
    # Initialize RAG components
    with app.app_context():
        try:
            init_components()
            app.logger.info("RAG pipeline initialized successfully")
        except Exception as e:
            app.logger.error(f"Failed to initialize RAG pipeline: {e}")
            # Continue without RAG components for health checks
    
    return app

def setup_logging(app):
    """Set up application logging."""
    
    # Set log level based on debug mode
    log_level = logging.DEBUG if app.config.get('DEBUG', False) else logging.INFO
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()  # Console output
        ]
    )
    
    # Set specific logger levels
    logging.getLogger('werkzeug').setLevel(logging.WARNING)  # Reduce Flask noise
    logging.getLogger('urllib3').setLevel(logging.WARNING)   # Reduce HTTP noise
    
    app.logger.info(f"Logging configured at level: {logging.getLevelName(log_level)}")
