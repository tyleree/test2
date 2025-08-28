"""
Gunicorn configuration for production deployment.
"""

import os

# WSGI module and application
wsgi_module = "wsgi:app"

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"
backlog = 2048

# Worker processes
workers = int(os.environ.get('WORKERS', 2))
worker_class = "sync"
worker_connections = 1000
threads = int(os.environ.get('THREADS', 4))

# Timeouts
timeout = 120
keepalive = 30
graceful_timeout = 30

# Logging
loglevel = "info"
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "rag-flask-app"

# Server mechanics
preload_app = True
daemon = False
pidfile = None
tmp_upload_dir = None

# SSL (configure if needed)
# keyfile = None
# certfile = None

# Worker recycling (helps with memory leaks)
max_requests = 1000
max_requests_jitter = 50

# Memory limits
# worker_tmp_dir = "/dev/shm"  # Use RAM disk if available

def when_ready(server):
    """Called when the server is ready to receive requests."""
    server.log.info("RAG Flask server is ready. Listening on: %s", server.address)

def worker_int(worker):
    """Called when a worker receives the INT or QUIT signal."""
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Called before a worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    """Called after a worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)
