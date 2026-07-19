# gunicorn.conf.py
# Production-ready Gunicorn config for Lyrica
# Start command: gunicorn -c gunicorn.config.py run:app

import multiprocessing
import os

# Workers formula: (2 * CPU) + 1 is a common heuristic.
# Cap at 4 for free-tier hosts (512MB RAM). WEB_CONCURRENCY overrides.
_cpu = multiprocessing.cpu_count()
workers = int(os.getenv("WEB_CONCURRENCY", min((_cpu * 2) + 1, 4)))

# gevent gives us async-friendly concurrency within each worker.
# Each worker handles many requests concurrently via green threads.
# Falls back to 'sync' if gevent is not installed (e.g. on Windows without C++ build tools).
try:
    import gevent  # noqa: F401
    worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gevent")
except ImportError:
    worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")
worker_connections = 1000   # max simultaneous connections per gevent worker

bind        = f"0.0.0.0:{os.getenv('PORT', '9999')}"
timeout     = 120          # Allow up to 120s for slow external APIs
keepalive   = 5
max_requests        = 1000    # Restart workers after 1000 requests (memory leak prevention)
max_requests_jitter = 100
preload_app = True           # Load app once, fork workers — saves RAM
accesslog   = "-"            # Log to stdout
errorlog    = "-"
loglevel    = os.getenv("LOG_LEVEL", "info").lower()
