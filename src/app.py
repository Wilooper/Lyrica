from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_compress import Compress
from src.logger import get_logger
from src import __version__
from src.router import register_routes
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os

# Admin cache endpoints
from src.cache import clear_cache, cache_stats
from src.config import ADMIN_KEY

def create_app():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    
    CORS(app, resources={r"/*": {"origins": "*", "allow_headers": ["Content-Type"], "expose_headers": ["Access-Control-Allow-Origin"]}})
    
    # Gzip compress all responses — reduces payload size by 60-80%
    Compress(app)
    
    app.logger = get_logger("Lyrica")
    app.config["VERSION"] = __version__
    
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
                    app.logger.warning(f"Global proxy URL invalid or already in pool (skipped)")
    except Exception as e:
        app.logger.warning(f"Failed to load PROXY_URL: {e}")
    
    # Rate limiting: per-IP key, default "15 per minute".
    # Use RATE_LIMIT_STORAGE_URI to set a Redis (recommended) or another backend.
    storage_uri = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=storage_uri,
        headers_enabled=True,
        default_limits=["15 per minute"],
    )
    limiter.init_app(app)
    
    # NEW: Admin helper function
    def admin_required(req):
        # Can pass key via query param or header
        key = req.args.get("key") or req.headers.get("X-ADMIN-KEY")
        return key == ADMIN_KEY
    
    # Custom 429 error handler: tell the client to wait 35 seconds.
    @app.errorhandler(429)
    def ratelimit_handler(e):
        resp = jsonify({
            "status": "error",
            "error": {
                "message": "Rate limit exceeded. Please wait 35 seconds before retrying.",
            }
        })
        resp.status_code = 429
        # Set Retry-After so clients / browsers / tooling know how long to wait
        resp.headers["Retry-After"] = "35"
        return resp
    
    # NEW: Secure admin endpoints
    @app.route("/admin/cache/clear", methods=["GET"])
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
    
    register_routes(app)
    return app
