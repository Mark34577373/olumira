import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flask_migrate import upgrade
from sqlalchemy import select, inspect, text
from sqlalchemy.exc import IntegrityError
from olumira import create_app
from olumira.extensions import db
from olumira.models import Owner, Routine, RoutineCompletion, Observation
from services.database import ensure_workspace, transaction
from services.data_transfer import backup_sqlite, read_snapshot, transfer_sqlite
from services.routines import get_routines, toggle_routine, delete_routine
from services.observations import add_observation


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.make_app('main.db')
        self.context = self.app.app_context()
        self.context.push()
        upgrade()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.temp.cleanup()

    def make_app(self, filename):
        return create_app({'APP_ENV': 'testing', 'DATABASE': str(self.root / filename)})

    def seed(self):
        ensure_workspace('fictional-test-owner')
        routine = get_routines('fictional-test-owner')[0]
        toggle_routine('fictional-test-owner', routine['id'])
        add_observation('fictional-test-owner', 'Fictional walk', '2026-10-16', 'Test only', 'Calm', 'test')
        # Preserve a legacy unowned routine; never silently reassign it.
        with transaction() as session:
            session.add(Routine(name='Legacy test', category='General', owner_id=None))
        return routine['id']

    def test_upgrade_repeatable_and_no_model_drift(self):
        self.seed()
        upgrade()
        self.assertEqual(len(get_routines('fictional-test-owner')), 5)
        from alembic.migration import MigrationContext
        from alembic.autogenerate import compare_metadata
        with db.engine.connect() as connection:
            changes = compare_metadata(MigrationContext.configure(connection), db.metadata)
            self.assertEqual(changes, [])

    def test_constraints_rollback_and_cascade(self):
        routine_id = self.seed()
        with self.assertRaises(IntegrityError):
            with transaction() as session:
                session.add(Observation(owner_id='fictional-test-owner', activity='Must roll back', date='2026-10-16'))
                session.add(RoutineCompletion(routine_id=routine_id, completion_date=__import__('services.database', fromlist=['today_string']).today_string()))
        self.assertEqual(db.session.scalar(select(db.func.count()).select_from(Observation)), 1)
        delete_routine('fictional-test-owner', routine_id)
        self.assertEqual(db.session.scalar(select(db.func.count()).select_from(RoutineCompletion)), 0)
        with self.assertRaises(IntegrityError):
            with transaction() as session:
                session.add(RoutineCompletion(routine_id=999999, completion_date='2026-10-16'))

    def test_transfer_preserves_records_and_refuses_nonempty_destination(self):
        self.seed()
        source = self.root / 'main.db'
        before = source.read_bytes()
        dest = self.make_app('destination.db')
        with dest.app_context():
            upgrade()
            counts = transfer_sqlite(source, self.root / 'backup.db')
            self.assertEqual(counts, {'owners': 1, 'routines': 6, 'observations': 1, 'routine_completions': 1})
            with self.assertRaises(ValueError):
                transfer_sqlite(source, self.root / 'second-backup.db')
            self.assertEqual(db.session.scalar(select(db.func.count()).select_from(Routine)), 6)
        self.assertEqual(before, source.read_bytes())
        self.assertEqual(read_snapshot(source), read_snapshot(self.root / 'backup.db'))

    def test_failed_transfer_rolls_back(self):
        self.seed()
        dest = self.make_app('rollback.db')
        with dest.app_context():
            upgrade()
            # Force a constraint failure after owner/routine inserts.
            with db.engine.begin() as conn:
                conn.exec_driver_sql("CREATE TRIGGER reject_test BEFORE INSERT ON observations BEGIN SELECT RAISE(ABORT, 'test'); END")
            with self.assertRaises(IntegrityError):
                transfer_sqlite(self.root / 'main.db', self.root / 'failure-backup.db')
            self.assertEqual(db.session.scalar(select(db.func.count()).select_from(Owner)), 0)
            self.assertEqual(db.session.scalar(select(db.func.count()).select_from(Routine)), 0)

    def test_backup_refuses_overwrite_and_invalid_source(self):
        self.seed()
        backup = self.root / 'backup.db'
        backup_sqlite(self.root / 'main.db', backup)
        with self.assertRaises(FileExistsError):
            backup_sqlite(self.root / 'main.db', backup)
        with self.assertRaises(ValueError):
            backup_sqlite(self.root / 'absent.db', self.root / 'new.db')

    def test_adopt_legacy_schema_preserves_records(self):
        legacy = self.make_app('legacy.db')
        with legacy.app_context():
            upgrade(revision='0001')
            self.seed()
            with db.engine.begin() as connection:
                connection.execute(text('DROP TABLE alembic_version'))
            result = legacy.test_cli_runner().invoke(args=['adopt-legacy-sqlite', '--backup', str(self.root / 'legacy-backup.db')])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(db.session.execute(text('SELECT version_num FROM alembic_version')).scalar(), '0001')
            db.session.rollback()
            upgrade()
            self.assertEqual(len(get_routines('fictional-test-owner')), 5)


    def test_separate_factories_have_isolated_databases(self):
        self.seed()
        other = self.make_app('other.db')
        with other.app_context():
            upgrade()
            self.assertEqual(db.session.scalar(select(db.func.count()).select_from(Routine)), 0)
        self.assertEqual(len(get_routines('fictional-test-owner')), 5)

    def test_legacy_transfer_refuses_to_drop_account_records(self):
        from services.authentication import register_user
        register_user('fictional-transfer@example.com', 'Fictional transfer', 'Fictional transfer passphrase 42')
        destination = self.make_app('account-destination.db')
        with destination.app_context():
            upgrade()
            with self.assertRaises(ValueError):
                transfer_sqlite(self.root / 'main.db', self.root / 'account-backup.db')
            self.assertEqual(db.session.scalar(select(db.func.count()).select_from(Owner)), 0)

    def test_day15_records_survive_day16_upgrade(self):
        from werkzeug.security import generate_password_hash
        from services.authentication import PASSWORD_METHOD
        from support import PASSWORD
        from olumira.models import User, AuthSession
        legacy = self.make_app('day15-accounts.db')
        digest = 'e' * 64
        user_id = '1' * 32
        password_hash = generate_password_hash(PASSWORD, method=PASSWORD_METHOD)
        with legacy.app_context():
            upgrade(revision='0002')
            ensure_workspace('legacy-account-owner')
            # Seed the actual Day 15 schema without referencing Day 16 model columns.
            with db.engine.begin() as connection:
                connection.execute(text('INSERT INTO users (id,email,password_hash,display_name,email_verified,created_at,updated_at,owner_id) VALUES (:id,:email,:hash,:name,:verified,:created,:created,:owner)'),
                    dict(id=user_id, email='fictional-legacy@example.com', hash=password_hash, name='Fictional legacy account',
                         verified=True, created='2026-10-16 12:00:00.000000', owner='legacy-account-owner'))
                connection.execute(text('INSERT INTO auth_sessions (token_hash,user_id,created_at,expires_at,last_seen_at,revoked_at) VALUES (:digest,:id,1,9999999999,1,NULL)'), dict(digest=digest, id=user_id))
            upgrade()
            user = db.session.get(User, user_id)
            self.assertEqual(user.password_hash, password_hash)
            self.assertTrue(user.email_verified)
            self.assertEqual(user.auth_version, 0)
            self.assertIsNone(user.pending_email)
            self.assertEqual(db.session.get(AuthSession, digest).auth_version, 0)
            self.assertEqual(db.session.get(AuthSession, digest).expires_at, 9999999999)
            self.assertEqual(len(get_routines('legacy-account-owner')), 5)
