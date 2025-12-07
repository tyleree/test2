# Gunicorn configuration for Veterans Benefits AI
# Increased timeouts for RAG system initialization with 1407 embeddings

# Worker timeout - allow 10 minutes for RAG initialization
timeout = 600

# Graceful timeout - allow workers to finish processing
graceful_timeout = 120

# Keep alive connections
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Worker configuration
workers = 1  # Single worker to conserve memory
worker_class = "sync"
threads = 2  # Allow some concurrency within the worker

# Preload application - initialize RAG before forking workers
preload_app = True

