"""WSGI entry point used by Gunicorn on Render (see Procfile)."""

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Local server. In production Gunicorn imports "app" above.
    # Reloading is disabled on purpose: the local JSON database is owned by a
    # single process, and a debug reloader would start a second process that
    # can overwrite data saved by the first one.
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
