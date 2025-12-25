import os
from dotenv import load_dotenv

load_dotenv()


# Base directory of project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Caching (Render safe)
CACHE_DIR = os.getenv("CACHE_DIR") or os.path.join(BASE_DIR, "cache_data")
CACHE_TTL = int(os.getenv("CACHE_TTL", 300))  # seconds

# Admin security key (MUST be set on Render)
ADMIN_KEY = os.getenv("ADMIN_KEY")


# logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# external tokens (must be provided via environment variables in production)
GENIUS_TOKEN = os.getenv("GENIUS_TOKEN", "")
YOUTUBE_COOKIE = os.getenv("YOUTUBE_COOKIE", "")

# lrclib
LRCLIB_API_URL = os.getenv("LRCLIB_API_URL", "https://lrclib.net/api/get")

# Rate limiting storage backend (recommended: Redis for production)
# Example: redis://:password@redis-host:6379/0
RATE_LIMIT_STORAGE_URI = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")
