"""Opt-in startup checks: read-only metadata, no records or raw exceptions."""
import json
import re
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from .extensions import db


def connection_status(error):
    """Fixed hints from libpq errors; never return message fragments or values."""
    message = str(getattr(error, 'orig', None) or error).lower()
    for status, phrases in (
        ('failed_tls_hostname', ('does not match host name', 'hostname mismatch')),
        ('failed_tls_trust', ('certificate verify failed', 'root certificate file', 'unknown ca')),
        ('failed_dns', ('could not translate host name', 'name or service not known', 'nodename nor servname')),
        ('failed_timeout', ('timeout expired', 'connection timed out')),
        ('failed_refused', ('connection refused',)),
        ('failed_authentication', ('password authentication failed', 'no password supplied')),
    ):
        if any(phrase in message for phrase in phrases):
            return status
    return 'failed'


def run(app):
    # Never infer enablement from production/Render and never expose an endpoint.
    if not app.config.get('OLUMIRA_DB_DIAGNOSTIC', False):
        return

    def emit(stage, status, **fields):
        app.logger.warning('database_diagnostic %s', json.dumps(
            dict(stage=stage, status=status, **fields), sort_keys=True))

    stage = 'migration_inventory'
    try:
        with app.app_context():
            from .models import (Owner, User, FamilyWorkspace, WorkspaceMembership,
                                 AuditEvent, Routine, RoutineStep, AccountToken,
                                 EmailOutbox, AuthSession)
            config = Config()
            config.set_main_option('script_location', str(Path(app.root_path).parent / 'migrations'))
            scripts = ScriptDirectory.from_config(config)
            known = {revision.revision for revision in scripts.walk_revisions()}
            expected = set(scripts.get_heads())
            stage = 'connection'
            with db.engine.connect() as connection:
                emit(stage, 'connected')
                with connection.begin():
                    # Server-enforced read-only transaction on the production DB.
                    if connection.dialect.name == 'postgresql':
                        connection.execute(text('SET TRANSACTION READ ONLY'))
                    stage = 'select_1'
                    assert connection.execute(text('SELECT 1')).scalar_one() == 1
                    emit(stage, 'ok')
                    inspector = inspect(connection)
                    stage = 'alembic_version'
                    present = inspector.has_table('alembic_version')
                    emit(stage, 'present' if present else 'missing')
                    if present:
                        revisions = connection.execute(text('SELECT version_num FROM alembic_version LIMIT 33')).scalars().all()
                        # Only repository revision IDs may enter logs, not arbitrary DB text.
                        current = [value if value in known else 'unrecognized' for value in revisions]
                        matches = len(revisions) <= 32 and set(revisions) == expected
                        emit('migration_revision', 'current' if matches else 'mismatch',
                             current=current, expected=sorted(expected))
                    for model in (Owner, User, FamilyWorkspace, WorkspaceMembership,
                                  AuditEvent, Routine, RoutineStep, AccountToken,
                                  EmailOutbox, AuthSession):
                        stage = 'registration_schema'
                        table = model.__table__
                        if not inspector.has_table(table.name):
                            emit(stage, 'missing_table', table=table.name)
                            continue
                        actual = {column['name'] for column in inspector.get_columns(table.name)}
                        # Missing names come only from static ORM metadata, never stored data.
                        missing = sorted(column.name for column in table.columns if column.name not in actual)
                        emit(stage, 'missing_columns' if missing else 'columns_present',
                             table=table.name, missing_columns=missing)
            emit('complete', 'finished')
    except Exception as error:
        original = getattr(error, 'orig', None)
        state = getattr(original, 'sqlstate', None)
        if not isinstance(state, str) or not re.fullmatch(r'[A-Z0-9]{5}', state):
            state = 'unavailable'
        emit(stage, connection_status(error) if stage == 'connection' else 'failed', error_class=type(error).__name__,
             db_error_class=type(original).__name__ if original is not None else 'none', sqlstate=state)
    finally:
        # Gunicorn may preload before forking: never leave diagnostic sockets pooled.
        with app.app_context():
            if not (db.engine.dialect.name == 'sqlite' and db.engine.url.database in {None, '', ':memory:'}):
                db.engine.dispose()
