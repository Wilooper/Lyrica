from flask import Flask, g, jsonify, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
from flask_compress import Compress
from src.logger import get_logger
from src import __version__
from src.router import register_routes
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
import hmac
import os
import time
import uuid
from datetime import datetime, timezone

# Admin cache endpoints
from src.cache import clear_cache, cache_stats
from src.config import ADMIN_KEY, RATE_LIMIT_STORAGE_URI as CONFIG_RATE_LIMIT_STORAGE_URI

_STARTED_AT = time.time()


try:  # Resolve once at import time: a failed ``import`` is expensive per call.
    import orjson as _orjson
except ImportError:  # pragma: no cover - depends on the environment
    _orjson = None


class _ORJSONProvider(DefaultJSONProvider):
    """Flask JSON provider backed by orjson when available.

    orjson is already a dependency for the cache layer; reusing it for HTTP
    responses avoids a second serialization implementation and is measurably
    faster for large lyrics payloads. Falls back to Flask's stdlib encoder for
    unsupported objects (or when orjson is not installed).
    """

    def dumps(self, obj, **kwargs):
        if _orjson is None:
            return super().dumps(obj, **kwargs)
        try:
            return _orjson.dumps(
                obj,
                default=self.default,
                option=_orjson.OPT_NON_STR_KEYS,
            ).decode("utf-8")
        except TypeError:
            return super().dumps(obj, **kwargs)

    def loads(self, s, **kwargs):
        if _orjson is None:
            return super().loads(s, **kwargs)
        return _orjson.loads(s)


def _is_production() -> bool:
    """Check if running in production mode (Docker / LYRICA_ENV=production)."""
    return os.getenv("LYRICA_ENV", "").lower() == "production"


def create_app():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.logger = get_logger("Lyrica")
    app.json = _ORJSONProvider(app)

    is_prod = _is_production()

    # ── Core safety limits ───────────────────────────────────────────────────
    # JSON bodies are only used by admin endpoints; cap them to stop trivial
    # memory-exhaustion requests. Query-string fields are bounded in router.py.
    app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_CONTENT_LENGTH", str(1024 * 1024)))
    app.config["JSON_SORT_KEYS"] = False
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = int(os.getenv("STATIC_CACHE_SECONDS", "3600"))

    # Honour X-Forwarded-* only when explicitly running behind a trusted proxy
    # (nginx, Traefik, Render, Railway). Without this, rate limiting sees the
    # proxy IP and every client shares one bucket.
    try:
        _trust_proxy_hops = int(os.getenv("TRUST_PROXY", "0"))
    except ValueError:
        _trust_proxy_hops = 0
    if _trust_proxy_hops > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=_trust_proxy_hops,
            x_proto=_trust_proxy_hops,
            x_host=_trust_proxy_hops,
        )

    # ── CORS ─────────────────────────────────────────────────────────────────
    if is_prod:
        # Production: restrict origins via CORS_ORIGINS env var (comma-separated)
        # Default: allow all (same as dev) — override in .env for stricter control
        allowed_origins = os.getenv("CORS_ORIGINS", "*")
        if allowed_origins != "*":
            allowed_origins = [o.strip() for o in allowed_origins.split(",") if o.strip()]
        else:
            app.logger.warning(
                "CORS_ORIGINS is '*' in production — set an explicit allow-list "
                "if the API is consumed from browsers."
            )
        CORS(app, resources={r"/*": {
            "origins": allowed_origins,
            "allow_headers": ["Content-Type", "Authorization", "X-ADMIN-KEY"],
            "expose_headers": ["Access-Control-Allow-Origin", "Retry-After", "X-Request-ID"],
            "max_age": 86400,  # Cache preflight for 24h
        }})
    else:
        CORS(app, resources={r"/*": {
            "origins": "*",
            "allow_headers": ["Content-Type", "Authorization", "X-ADMIN-KEY"],
            "expose_headers": ["Access-Control-Allow-Origin", "Retry-After", "X-Request-ID"],
        }})

    # Gzip compress all responses — reduces payload size by 60-80%
    Compress(app)

    # Correlate logs and responses. Incoming IDs are reused when present so a
    # request can be traced across the reverse proxy, API, and fetchers.
    @app.before_request
    def _attach_request_id():
        incoming = request.headers.get("X-Request-ID", "")
        # Only accept a conservative character set: response header values with
        # control characters would raise inside Werkzeug's header validation.
        incoming = "".join(
            ch for ch in incoming[:64] if ch.isalnum() or ch in "-_."
        )
        g.request_id = incoming or uuid.uuid4().hex

    @app.after_request
    def _attach_response_request_id(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        return response

    app.config["VERSION"] = __version__
    app.config["IS_PRODUCTION"] = is_prod

    if is_prod:
        app.logger.info("=" * 60)
        app.logger.info("  LYRICA PRODUCTION MODE ACTIVE")
        app.logger.info("=" * 60)

    # ── Load user config (.lyrica.config) — must happen before routes ────────
    try:
        from src.user_config import load_user_config
        user_cfg = load_user_config()
        app.config["USER_CONFIG"] = user_cfg
        app.logger.info(f"User config loaded: {user_cfg.config_path or 'defaults'}")
    except Exception as e:
        app.logger.warning(f"User config load failed (proceeding with defaults): {e}")
        app.config["USER_CONFIG"] = None

    # ── Global proxy pool — seed from PROXY_URL env var ───────────────────────
    # PROXY_URL is for ALL fetchers. Supports a single URL or comma-separated list.
    # YT_PROXY_URL remains YouTube-only (handled inside youtube_fetcher.py).
    try:
        from src.proxy_manager import get_proxy_manager as _get_pm
        proxy_env = os.getenv("PROXY_URL", "").strip()
        if proxy_env:
            _pm = _get_pm()
            for _url in [u.strip() for u in proxy_env.split(",") if u.strip()]:
                if _pm.add(_url):
                    app.logger.info(f"Global proxy loaded from PROXY_URL env var: {_url[:20]}***")
                else:
                    app.logger.warning("Global proxy URL invalid or already in pool (skipped)")
    except Exception as e:
        app.logger.warning(f"Failed to load PROXY_URL: {e}")

    # ── Rate Limiting ────────────────────────────────────────────────────────
    # Production: stricter limits; Dev: relaxed
    storage_uri = os.getenv("RATE_LIMIT_STORAGE_URI") or CONFIG_RATE_LIMIT_STORAGE_URI
    if is_prod:
        default_rate = os.getenv("RATE_LIMIT_DEFAULT", "60 per minute")
        if str(storage_uri).startswith("memory"):
            app.logger.warning(
                "Rate limiting uses per-process memory storage. With multiple "
                "Gunicorn workers the effective limit is multiplied by the worker "
                "count — set RATE_LIMIT_STORAGE_URI to Redis in production."
            )
    else:
        default_rate = "15 per minute"

    limiter_enabled = os.getenv("RATELIMIT_ENABLED", "true").lower() in ("true", "1", "yes") and app.config.get("RATELIMIT_ENABLED", True)
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=storage_uri,
        headers_enabled=True,
        default_limits=[default_rate],
        enabled=limiter_enabled,
    )
    limiter.init_app(app)

    # Secure admin helper function (constant-time comparison)
    def admin_required(req):
        if not ADMIN_KEY:
            return False
        # Header is preferred; query param kept for backwards compatibility.
        key = req.headers.get("X-ADMIN-KEY") or req.args.get("key")
        return bool(key and hmac.compare_digest(str(key), str(ADMIN_KEY)))

    # ── Security Headers (production only) ───────────────────────────────────
    if is_prod:
        @app.after_request
        def add_security_headers(response):
            # Prevent MIME sniffing
            response.headers["X-Content-Type-Options"] = "nosniff"
            # Prevent clickjacking
            response.headers["X-Frame-Options"] = "DENY"
            # XSS protection
            response.headers["X-XSS-Protection"] = "1; mode=block"
            # Referrer policy
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            # Strict Transport Security (HTTPS)
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            # Content Security Policy
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "connect-src 'self' https:; "
                "font-src 'self' https: data:; "
                "frame-ancestors 'none'"
            )
            # Remove server identification header
            response.headers.pop("Server", None)
            return response

    # ── Error Handlers ───────────────────────────────────────────────────────

    # Custom 429 error handler. Retry-After is derived from the limiter when
    # available, otherwise falls back to the default window.
    @app.errorhandler(429)
    def ratelimit_handler(e):
        retry_after = int(getattr(e, "retry_after", 0) or 60)
        resp = jsonify({
            "status": "error",
            "error": {
                "message": f"Rate limit exceeded. Please wait {retry_after} seconds before retrying.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        })
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    @app.errorhandler(404)
    def not_found_handler(e):
        return jsonify({
            "status": "error",
            "error": {
                "message": "Endpoint not found",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        }), 404

    @app.errorhandler(405)
    def method_not_allowed_handler(e):
        return jsonify({
            "status": "error",
            "error": {
                "message": "Method not allowed",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        }), 405

    @app.errorhandler(413)
    def request_too_large_handler(e):
        return jsonify({
            "status": "error",
            "error": {
                "message": "Request body too large",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        }), 413

    @app.errorhandler(500)
    def internal_error_handler(e):
        app.logger.error("Internal server error: %s", e)
        return jsonify({
            "status": "error",
            "error": {
                "message": "Internal server error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        }), 500

    # ── Admin Endpoints ──────────────────────────────────────────────────────

    @app.route("/admin/cache/clear", methods=["POST"])
    def admin_clear_cache():
        if not admin_required(request):
            return {"error": "unauthorized"}, 403
        result = clear_cache()
        return {"status": "cache cleared", "details": result}

    @app.route("/admin/cache/stats", methods=["GET"])
    def admin_cache_stats():
        if not admin_required(request):
            return {"error": "unauthorized"}, 403
        return cache_stats()

    # ── Health Check Endpoints ───────────────────────────────────────────────
    @app.route("/health", methods=["GET"])
    def health_check():
        """Liveness probe — deliberately does no network I/O.

        A health check that pings Redis on every probe can block a worker and
        cause the orchestrator to kill a perfectly healthy container. Use
        /health/ready for dependency checks.
        """
        return jsonify({
            "status": "healthy",
            "version": __version__,
            "service": "Lyrica",
            "mode": "production" if is_prod else "development",
            "uptime_seconds": round(time.time() - _STARTED_AT, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @app.route("/health/ready", methods=["GET"])
    def readiness_check():
        """Readiness probe — verifies optional Redis connectivity."""
        from src.cache import get_redis_client
        redis_ok = False
        try:
            rc = get_redis_client()
            if rc:
                rc.ping()
                redis_ok = True
        except Exception:
            pass

        body = {
            "status": "ready",
            "version": __version__,
            "service": "Lyrica",
            "redis": "connected" if redis_ok else "unavailable",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Redis is an optional cache tier, so absence is not fatal. Report 200
        # for liveness semantics and expose the dependency state in the body.
        return jsonify(body)

    register_routes(app)
    limiter.exempt(health_check)
    limiter.exempt(readiness_check)
    return app


# Top-level instance for Vercel / serverless platforms that import src/app.py directly
app = create_app()
