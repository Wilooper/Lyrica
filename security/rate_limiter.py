import time
from collections import defaultdict

REQUEST_LIMIT = int(os.getenv("RATE_LIMIT_PER_MINUTE", 15))
WINDOW = 60

_requests = defaultdict(list)

def is_rate_limited(ip):
    now = time.time()
    _requests[ip] = [t for t in _requests[ip] if now - t < WINDOW]

    if len(_requests[ip]) >= REQUEST_LIMIT:
        return True

    _requests[ip].append(now)
    return False
