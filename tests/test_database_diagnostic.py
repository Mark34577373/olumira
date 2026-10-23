"""Temporary startup checks are opt-in, read-only and privacy preserving."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask_migrate import upgrade
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from psycopg import OperationalError as PGOperationalError

from olumira import create_app
from olumira.config import configuration
from olumira.extensions import db
from olumira.database_diagnostic import run


def records(caplog):
    return [json.loads(record.getMessage().split('database_diagnostic ',1)[1])
            for record in caplog.records if record.getMessage().startswith('database_diagnostic ')]


@pytest.fixture
def app(tmp_path):
    app=create_app(dict(APP_ENV='testing',DATABASE=str(tmp_path/'diagnostic.db'),OLUMIRA_DB_DIAGNOSTIC=False))
    yield app
    with app.app_context():db.session.remove();db.engine.dispose()


def test_disabled_never_accesses_app_or_database():
    run(SimpleNamespace(config={}))
    for value in ('0','true','yes',''):
        with patch.dict('os.environ',{'OLUMIRA_DB_DIAGNOSTIC':value}):
            assert not configuration({'APP_ENV':'testing'})['OLUMIRA_DB_DIAGNOSTIC']
    with patch.dict('os.environ',{'OLUMIRA_DB_DIAGNOSTIC':'1'}):
        assert configuration({'APP_ENV':'testing'})['OLUMIRA_DB_DIAGNOSTIC']


def test_factory_flag_runs_missing_schema_probe_once(tmp_path,caplog):
    create_app(dict(APP_ENV='testing',DATABASE=str(tmp_path/'empty.db'),OLUMIRA_DB_DIAGNOSTIC=True))
    events=records(caplog)
    assert sum(e['stage']=='select_1' and e['status']=='ok' for e in events)==1
    assert any(e['stage']=='alembic_version' and e['status']=='missing' for e in events)
    assert any(e.get('table')=='users' and e['status']=='missing_table' for e in events)


def test_migrated_schema_and_rows_unchanged(app,caplog):
    with app.app_context():
        upgrade()
        db.session.execute(text("INSERT INTO owners(id,created_at) VALUES ('FICTIONAL-PRIVATE-SENTINEL','2026-10-22')"));db.session.commit()
    # Alembic's logging fileConfig replaces pytest's root capture handlers.
    app.logger.addHandler(caplog.handler)
    try:
        app.config['OLUMIRA_DB_DIAGNOSTIC']=True;run(app)
    finally:
        app.logger.removeHandler(caplog.handler)
    events=records(caplog)
    assert any(e['stage']=='migration_revision' and e['status']=='current' and e['current']==['0022'] for e in events)
    tables=[e for e in events if e['stage']=='registration_schema']
    assert len(tables)==10 and all(e['status']=='columns_present' for e in tables)
    assert 'FICTIONAL-PRIVATE-SENTINEL' not in caplog.text
    with app.app_context():
        assert db.session.execute(text('SELECT id FROM owners')).scalars().all()==['FICTIONAL-PRIVATE-SENTINEL']


def test_missing_column_and_unknown_revision_are_sanitized(app,caplog):
    with app.app_context():
        with db.engine.begin() as connection:
            connection.execute(text('CREATE TABLE alembic_version(version_num TEXT)'))
            connection.execute(text("INSERT INTO alembic_version VALUES ('PRIVATE-REVISION-TOKEN')"))
            connection.execute(text('CREATE TABLE users(id TEXT, email TEXT)'))
    app.config['OLUMIRA_DB_DIAGNOSTIC']=True;run(app)
    events=records(caplog)
    assert any(e['stage']=='migration_revision' and e['current']==['unrecognized'] for e in events)
    assert any(e.get('table')=='users' and 'password_hash' in e['missing_columns'] for e in events)
    assert 'PRIVATE-REVISION-TOKEN' not in caplog.text


@pytest.mark.parametrize('message,status',[
    ('root certificate file /PRIVATE-PATH does not exist','failed_tls_trust'),
    ('certificate verify failed PRIVATE-HOST','failed_tls_trust'),
    ('certificate does not match host name PRIVATE-HOST','failed_tls_hostname'),
    ('could not translate host name PRIVATE-HOST','failed_dns'),
    ('connection timed out PRIVATE-HOST','failed_timeout'),
    ('connection refused PRIVATE-HOST','failed_refused'),
    ('password authentication failed for PRIVATE-USER','failed_authentication'),
    ('PRIVATE-RAW-ERROR','failed'),
])
def test_connection_failure_does_not_reveal_messages(app,caplog,message,status):
    error=OperationalError('PRIVATE-SQL',{'password':'PRIVATE-PASSWORD'},PGOperationalError(message))
    app.config['OLUMIRA_DB_DIAGNOSTIC']=True
    with app.app_context():
        with patch.object(db.engine,'connect',side_effect=error):run(app)
    event=records(caplog)[0]
    assert event==dict(stage='connection',status=status,error_class='OperationalError',db_error_class='OperationalError',sqlstate='unavailable')
    assert 'PRIVATE-' not in caplog.text


def test_postgres_probe_enforces_read_only_before_queries(app,caplog):
    from unittest.mock import MagicMock
    connection=MagicMock();connection.dialect.name='postgresql'
    connection.execute.return_value.scalar_one.return_value=1
    inspector=MagicMock();inspector.has_table.return_value=False
    app.config['OLUMIRA_DB_DIAGNOSTIC']=True
    with app.app_context():
        with patch.object(db.engine,'connect') as connect, patch.object(db.engine,'dispose') as dispose, patch('olumira.database_diagnostic.inspect',return_value=inspector):
            connect.return_value.__enter__.return_value=connection
            run(app)
            assert [str(call.args[0]) for call in connection.execute.call_args_list]==['SET TRANSACTION READ ONLY','SELECT 1']
            dispose.assert_called_once()
    assert any(e['stage']=='complete' for e in records(caplog))


def test_registration_recovers_after_connection_failure(app):
    from support import post, PASSWORD
    from olumira.models import User
    from sqlalchemy import select
    with app.app_context():upgrade()
    client=app.test_client()
    data=dict(display_name='Fictional recovery',email='fictional-recovery@example.com',password=PASSWORD,confirm_password=PASSWORD)
    # Obtain CSRF before interrupting connectivity; no verification is bypassed.
    from support import csrf_token
    data['csrf_token']=csrf_token(client)
    error=OperationalError('PRIVATE-SQL',{},PGOperationalError('connection refused PRIVATE-HOST'))
    with app.app_context():
        with patch.object(db.engine,'connect',side_effect=error):
            response=client.post('/auth/register',data=data)
    assert response.status_code==500
    with app.app_context():assert db.session.scalar(select(User.id).where(User.email==data['email'])) is None
    data.pop('csrf_token')  # The helper visits login afresh; use its current token.
    response=post(client,'/auth/register',data)
    assert response.status_code==302 and response.location=='/auth/check-email'
    with app.app_context():assert db.session.scalar(select(User.id).where(User.email==data['email'])) is not None
