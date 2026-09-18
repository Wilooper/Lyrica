from src.app import create_app
import os

app = create_app()

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.getenv("PORT", 9999))
    # threaded=True gives production-level concurrency even on local machine
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)


