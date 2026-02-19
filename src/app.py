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
    app = Flask(__name__, template_folder="templates", static_folder="static")
    
    CORS(app, resources={r"/*": {"origins": "*", "allow_headers": ["Content-Type"], "expose_headers": ["Access-Control-Allow-Origin"]}})
    
    # Gzip compress all responses — reduces payload size by 60-80%
    Compress(app)
    
    app.logger = get_logger("Lyrica")
    app.config["VERSION"] = __version__
    
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
