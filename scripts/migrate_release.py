"""Operator-only migration with separate credentials and a PostgreSQL advisory lock."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    import psycopg
    from sqlalchemy.engine import make_url
    from flask_migrate import upgrade
    from olumira import create_app

    url = os.environ.get("MIGRATION_DATABASE_URL", "")
    if not url:
        raise ValueError(
            "MIGRATION_DATABASE_URL is required in the isolated release job"
        )
    app = create_app({"DATABASE_URL": url})
    parsed = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    # A dedicated connection holds the lock throughout migration; workers never migrate.
    parameters = dict(parsed.query)
    parameters.update(
        host=parsed.host or parameters.get("host"),
        port=parsed.port or parameters.get("port", 5432),
        dbname=parsed.database,
        user=parsed.username,
        password=parsed.password,
        connect_timeout=3,
    )
    with psycopg.connect(**parameters) as connection:
        locked = connection.execute("SELECT pg_try_advisory_lock(438143)").fetchone()[0]
        if not locked:
            raise RuntimeError("Another migration is active")
        try:
            with app.app_context():
                upgrade()
        finally:
            connection.execute("SELECT pg_advisory_unlock(438143)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Release migration failed; inspect privately. No connection details logged.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
