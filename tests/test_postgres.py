"""Opt-in integration test. Requires an explicitly disposable, empty PostgreSQL DB."""
import os
import tempfile
import unittest
from pathlib import Path
from flask_migrate import upgrade
from sqlalchemy import inspect, select
from olumira import create_app
from olumira.extensions import db
from olumira.models import Routine
from services.database import ensure_workspace
from services.data_transfer import transfer_sqlite
from services.routines import get_routines, toggle_routine


@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'), 'No disposable TEST_POSTGRES_URL configured')
class PostgreSQLIntegrationTests(unittest.TestCase):
    def test_migration_transfer_and_sequence(self):
        url = os.environ['TEST_POSTGRES_URL']
        self.assertTrue(url.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg://')))
        target = create_app({'APP_ENV': 'testing', 'DATABASE_URL': url})
        with tempfile.TemporaryDirectory() as temp:
            source_path = Path(temp) / 'source.db'
            source = create_app({'APP_ENV': 'testing', 'DATABASE': str(source_path)})
            with source.app_context():
                upgrade()
                ensure_workspace('fictional-postgres-test')
                item = get_routines('fictional-postgres-test')[0]
                toggle_routine('fictional-postgres-test', item['id'])
                db.session.remove()
                db.engine.dispose()
            with target.app_context():
                # Refuse to touch any existing schema, including an earlier test run.
                self.assertEqual(inspect(db.engine).get_table_names(), [], 'Use a new empty disposable PostgreSQL database')
                try:
                    upgrade()
                    upgrade()
                    counts = transfer_sqlite(source_path, Path(temp) / 'backup.db')
                    self.assertEqual(counts['routine_completions'], 1)
                    self.assertEqual(get_routines('fictional-postgres-test')[0]['completed'], 1)
                    from services.routines import add_routine
                    self.assertEqual(add_routine('fictional-postgres-test', 'Next task', 'General'), 'ok')
                    self.assertGreater(get_routines('fictional-postgres-test')[-1]['id'], 5)
                finally:
                    db.session.remove()
                    db.engine.dispose()
        # Keep the disposable database for inspection; never auto-drop tables.
