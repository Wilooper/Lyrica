# ============================================================
# Lyrica API — Production Dockerfile (multi-stage)
#
# Usage:
#   docker build -t lyrica .
#   docker run -d --name lyrica -p 7860:7860 --env-file .env lyrica
#
# Or with docker compose:
#   docker compose up -d
#
# Features:
#   - Multi-stage build (smaller final image)
#   - Non-root user for security
#   - Health checks built in
#   - Aggressive production defaults
#   - Optimized layer caching
# ============================================================

# ── Stage 1: Builder ─────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies in a separate layer (cached unless requirements change)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential gcc git libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Production Runtime ──────────────────────────────
FROM python:3.11-slim AS runtime

# Labels for container metadata
LABEL maintainer="Lyrica <https://github.com/Wilooper/Lyrica>" \
      version="1.5.0" \
      description="Lyrica — Production-grade lyrics aggregation API"

# Environment defaults for production
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # ── App defaults ──
    PORT=7860 \
    LYRICA_ENV=production \
    LOG_LEVEL=WARNING \
    # ── Gunicorn production tuning ──
    WEB_CONCURRENCY=4 \
    GUNICORN_WORKER_CLASS=gthread \
    GUNICORN_THREADS=16 \
    # ── Cache defaults (aggressive for production) ──
    CACHE_TTL=604800 \
    CACHE_DIR=/app/cache_data \
    # ── Security ──
    PYTHONPATH=/app

WORKDIR /app

# Install only runtime dependencies (no build tools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg curl tini libxml2 libxslt1.1 && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user and writable runtime directories
RUN groupadd -r lyrica && \
    useradd -r -g lyrica -d /app -s /sbin/nologin lyrica && \
    mkdir -p /app/cache_data /app/logs && \
    chown -R lyrica:lyrica /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=lyrica:lyrica . /app

# Overwrite gunicorn config with production-hardened version
COPY --chown=lyrica:lyrica gunicorn_production.py /app/gunicorn_production.py

# Health check — lightweight liveness endpoint (no Redis/network I/O)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:${PORT}/health || exit 1

EXPOSE ${PORT}

# Switch to non-root user
USER lyrica

# Use tini as PID 1 for proper signal handling (SIGTERM → graceful shutdown)
ENTRYPOINT ["tini", "--"]

# Start Gunicorn with production config
CMD ["gunicorn", "-c", "gunicorn_production.py", "run:app"]
