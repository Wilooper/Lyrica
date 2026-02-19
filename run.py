from src.app import create_app
import os

app = create_app()

if __name__ == "__main__":
    # Dev server only — never use in production.
    # Production: gunicorn -w 2 -b 0.0.0.0:9999 run:app
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.getenv("PORT", 9999))
    app.run(host="0.0.0.0", port=port, debug=debug)

