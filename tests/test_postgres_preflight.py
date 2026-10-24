"""Operator preflight uses catalog metadata, readonly SQL and sanitized output."""
from unittest.mock import MagicMock,patch
import json
import pytest
from psycopg import OperationalError
from scripts.postgres_preflight import check,parameters,main


def test_url_requires_verified_explicit_trust_and_no_conflicting_identity():
    url='postgresql://PRIVATE-USER:PRIVATE-PASSWORD@PRIVATE-HOST/db?sslmode=verify-full&sslrootcert=/PRIVATE-CA'
    params=parameters(url)
    assert params['sslmode']=='verify-full' and params['sslrootcert']=='/PRIVATE-CA'
    for bad in (url.replace('verify-full','require'),url+'&host=PRIVATE-OTHER',url+'&sslmode=verify-full'):
        with pytest.raises(ValueError):parameters(bad)


def test_hidden_schema_is_reported_without_names_or_records():
    connection=MagicMock()
    def execute(sql,args=None):
        result=MagicMock()
        if 'current_database()' in sql:result.fetchone.return_value=('PRIVATE-DB','PRIVATE-ROLE','public',['public'],180006)
        elif 'c.relkind IN' in sql:result.fetchall.return_value=[('PRIVATE-SCHEMA','users',False,False,False),('PRIVATE-SCHEMA','PRIVATE-TABLE',False,False,False)]
        elif 'count(*)' in sql:result.fetchone.return_value=(0,)
        elif 'SELECT EXISTS' in sql:result.fetchone.return_value=(True,)
        elif 'SELECT has_schema' in sql:result.fetchone.return_value=(True,False)
        return result
    connection.execute.side_effect=execute
    report=check(connection,'PRIVATE-DB','PRIVATE-ROLE','public')
    assert report['database_matches'] and report['role_matches'] and report['active_schema_matches']
    assert report['auth_relations']['users']==dict(catalog_present=True,in_expected_schema=False,visible=False,selectable=False)
    assert 'PRIVATE-' not in json.dumps(report)
    assert connection.execute.call_args_list[0].args[0]=='SET TRANSACTION READ ONLY'
    assert all(not call.args[0].startswith(('INSERT','UPDATE','DELETE','CREATE','ALTER','DROP')) for call in connection.execute.call_args_list)


def test_cli_failure_never_prints_connection_error(capsys):
    with patch('sys.stdin.isatty',return_value=True),patch('getpass.getpass',side_effect=['postgresql://PRIVATE:PRIVATE@PRIVATE/db?sslmode=verify-full&sslrootcert=system','PRIVATE','PRIVATE','public']),patch('psycopg.connect',side_effect=OperationalError('PRIVATE-ERROR')):
        assert main()==1
    assert 'PRIVATE' not in capsys.readouterr().out


def test_full_postgresql_upgrade_chain_compiles_without_connecting():
    import io
    from contextlib import redirect_stdout
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from flask_migrate import upgrade
    from olumira import create_app
    config=Config();config.set_main_option('script_location','migrations')
    scripts=ScriptDirectory.from_config(config)
    assert scripts.get_heads()==['0022'] and len(list(scripts.walk_revisions()))==22
    app=create_app(dict(APP_ENV='testing',DATABASE_URL='postgresql+psycopg://localhost/fictional',OLUMIRA_DB_DIAGNOSTIC=False))
    output=io.StringIO()
    with app.app_context(),redirect_stdout(output):upgrade(sql=True)
    sql=output.getvalue()
    for table in ('owners','users','auth_sessions','care_plans','handoff_drafts'):
        assert 'CREATE TABLE '+table in sql
    assert "version_num='0022'" in sql or "version_num='0022'" in sql.replace(' ','')
    assert not any(statement in sql.upper() for statement in ('DROP TABLE','TRUNCATE TABLE'))
