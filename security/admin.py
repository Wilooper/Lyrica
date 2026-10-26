"""Admin-key verification helper.

Kept for compatibility with integrations importing this module. The Flask app
uses the same constant-time comparison internally.
"""

import hmac
import os
from typing import Any


def verify_admin(request: Any) -> bool:
    admin_key = os.getenv("ADMIN_KEY")
    supplied = request.headers.get("X-ADMIN-KEY")
    if not admin_key or not supplied:
        return False
    return hmac.compare_digest(str(supplied), str(admin_key))
