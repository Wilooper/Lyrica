import os

def verify_admin(request):
    admin_key = request.headers.get("X-Admin-Key")
    return admin_key and admin_key == os.getenv("ADMIN_KEY")
