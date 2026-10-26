from src.app import app
import os

# Importing the already-created app avoids running create_app() twice (src.app
# builds one instance for serverless platforms; run.py used to build another).

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.getenv("PORT", 9999))
    # threaded=True gives production-level concurrency even on local machine
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)


