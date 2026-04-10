import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 8050))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(host=host, port=port, debug=debug, use_reloader=True, threaded=True)
