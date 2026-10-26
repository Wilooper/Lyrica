# gunicorn_production.py
# ============================================================
# Production-hardened Gunicorn config for Lyrica Docker deployments
#
# This config is optimized for high-concurrency, stability, and
# security in containerized production environments.
#
# Start: gunicorn -c gunicorn_production.py run:app
# ============================================================

import multiprocessing
import os

# ── Workers ──────────────────────────────────────────────────────────────────
# Formula: min(WEB_CONCURRENCY, (2 * CPU) + 1)
# Docker containers typically get 1-4 CPUs; WEB_CONCURRENCY overrides.
_cpu = multiprocessing.cpu_count()
workers = int(os.getenv("WEB_CONCURRENCY", min((_cpu * 2) + 1, 8)))

# ── Concurrency Strategy ────────────────────────────────────────────────────
# The application bridges async fetchers into synchronous Flask views using a
# per-thread asyncio event loop. Native threads (gthread) are the safe pairing
# for that bridge: each thread owns one loop and one pooled HTTP client.
#
# Gevent remains available via GUNICORN_WORKER_CLASS=gevent, but its
# monkey-patching of sockets/time can conflict with asyncio, so it is no longer
# the default.
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "gthread")
threads = int(os.getenv("GUNICORN_THREADS", "16"))
worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "500"))

# ── Binding ──────────────────────────────────────────────────────────────────
bind = f"0.0.0.0:{os.getenv('PORT', '7860')}"

# ── Timeouts ─────────────────────────────────────────────────────────────────
timeout = 180           # Allow up to 180s for slow external APIs / LLM translation
graceful_timeout = 30   # Wait 30s for in-flight requests on shutdown
keepalive = 5           # Keep TCP connections alive for 5s (reuse for pipelining)

# ── Worker Lifecycle (Stability) ─────────────────────────────────────────────
max_requests = 5000         # Restart workers after 5000 requests (prevents memory leaks)
max_requests_jitter = 500   # Randomize restart to avoid thundering herd
worker_tmp_dir = "/dev/shm" # Use RAM-backed tmpfs for heartbeat (faster, avoids disk I/O)

# ── App Loading ──────────────────────────────────────────────────────────────
preload_app = True      # Load app once in master, then fork workers (saves RAM)

# ── Logging ──────────────────────────────────────────────────────────────────
accesslog = "-"         # Log to stdout (Docker best practice)
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "warning").lower()

# ── Security Headers ────────────────────────────────────────────────────────
# forwarded_allow_ips: trust reverse proxy headers from these IPs
# In Docker/k8s, the reverse proxy (nginx/traefik) is typically on the same network
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "*")

# Limit request sizes to prevent abuse
limit_request_line = 8190       # Max URL length
limit_request_fields = 100      # Max number of headers
limit_request_field_size = 8190 # Max header value size

# ── Server Hooks ─────────────────────────────────────────────────────────────
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("🚀 Lyrica production server starting...")
    server.log.info(f"   Workers: {workers} × {worker_class}")
    if worker_class == "gevent":
        server.log.info(f"   Connections per worker: {worker_connections}")
    server.log.info(f"   Bind: {bind}")
    server.log.info(f"   Max requests: {max_requests} ±{max_requests_jitter}")
    server.log.info(f"   Timeout: {timeout}s | Graceful: {graceful_timeout}s")


def post_fork(server, worker):
    """Called after a worker is forked."""
    server.log.info(f"   Worker {worker.pid} spawned")


def worker_exit(server, worker):
    """Called when a worker exits."""
    server.log.info(f"   Worker {worker.pid} exited")


def on_exit(server):
    """Called just before the master process exits."""
    server.log.info("🛑 Lyrica production server shutting down")
