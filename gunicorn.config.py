# gunicorn.conf.py
# Render free tier: 512MB RAM, 1 vCPU
# Start command: gunicorn -c gunicorn.conf.py run:app

import multiprocessing
import os

# 2 workers is safe for 512MB RAM
# Formula: (2 * CPU cores) + 1, capped at 2 for free tier
workers = int(os.getenv("WEB_CONCURRENCY", 2))

# Use gevent worker for async-friendly concurrency (optional, requires: pip install gevent)
# worker_class = "gevent"
worker_class = "sync"

bind = f"0.0.0.0:{os.getenv('PORT', '9999')}"
timeout = 120          # Allow up to 120s for slow external APIs
keepalive = 5
max_requests = 1000    # Restart workers after 1000 requests to prevent memory leaks
max_requests_jitter = 100
preload_app = True     # Load app once, fork workers — saves RAM
accesslog = "-"        # Log to stdout (Render captures this)
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
