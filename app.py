"""Compatibility entry point for `gunicorn app:app` and Flask CLI."""
from olumira import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
