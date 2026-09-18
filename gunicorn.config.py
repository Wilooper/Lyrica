# gunicorn.config.py
# Production-ready Gunicorn config for Lyrica
# Start command: gunicorn -c gunicorn.config.py run:app

import multiprocessing
import os

# Workers formula: (2 * CPU) + 1 capped at 4 for standard containers. WEB_CONCURRENCY overrides.
_cpu = multiprocessing.cpu_count()
workers = int(os.getenv("WEB_CONCURRENCY", min((_cpu * 2) + 1, 4)))

# Concurrency strategy:
# Try gevent (greenlets), fallback to gthread (native OS threads) for multi-threaded async handling.
try:
    import gevent  # noqa: F401
    worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gevent")
    worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "1000"))
except ImportError:
    worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")
    threads = int(os.getenv("GUNICORN_THREADS", "8"))
    worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "250"))

bind        = f"0.0.0.0:{os.getenv('PORT', '9999')}"
timeout     = 120          # Allow up to 120s for slow external APIs / LLM translation
keepalive   = 5
max_requests        = 2000    # Restart workers after 2000 requests (memory leak prevention)
max_requests_jitter = 200
preload_app = True           # Load app once, fork workers — saves RAM
accesslog   = "-"            # Log to stdout
errorlog    = "-"
loglevel    = os.getenv("LOG_LEVEL", "info").lower()
