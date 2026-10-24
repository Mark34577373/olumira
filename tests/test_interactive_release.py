"""Manual release requires both preflight and typed confirmation."""
from unittest.mock import patch,MagicMock
from scripts.migrate_release_interactive import main


def test_cancel_never_runs_migrations(capsys):
    with patch('sys.stdin.isatty',return_value=True),patch('scripts.migrate_release_interactive.prepare',return_value={'MIGRATION_DATABASE_URL':'PRIVATE-URL'}),patch('builtins.input',return_value=''),patch('subprocess.run') as run:
        assert main()==0
        run.assert_not_called()
    assert 'PRIVATE-URL' not in capsys.readouterr().out


def test_prepare_failure_never_runs_migrations_or_logs_secrets(capsys):
    with patch('sys.stdin.isatty',return_value=True),patch('scripts.migrate_release_interactive.prepare',side_effect=ValueError('PRIVATE-ERROR')),patch('subprocess.run') as run:
        assert main()==1
        run.assert_not_called()
    assert 'PRIVATE-ERROR' not in capsys.readouterr().out


def test_explicit_confirmation_calls_only_existing_runner(capsys):
    env={'MIGRATION_DATABASE_URL':'PRIVATE-URL'}
    with patch('sys.stdin.isatty',return_value=True),patch('scripts.migrate_release_interactive.prepare',return_value=env),patch('builtins.input',return_value='MIGRATE 0022'),patch('subprocess.run',return_value=MagicMock(returncode=0)) as run:
        assert main()==0
    assert run.call_args.args[0][1].endswith('/scripts/migrate_release.py')
    assert 'PRIVATE-URL' not in str(run.call_args.args) and run.call_args.kwargs['env']==env
    assert 'PRIVATE-URL' not in capsys.readouterr().out


def test_prepare_validates_production_settings_without_writing(capsys):
    from cryptography.fernet import Fernet
    from scripts.migrate_release_interactive import prepare
    url='postgresql://olumira_user:PRIVATE-PASSWORD@PRIVATE-HOST/olumira?sslmode=verify-full&sslrootcert=/etc/ssl/cert.pem'
    inputs=[url,'olumira','olumira_user','public','fictional-production-secret-of-sufficient-length',Fernet.generate_key().decode(),'rediss://private.invalid/0','Olumira <test-sender@example.com>','smtp.example.com','PRIVATE-SMTP-USER','PRIVATE-SMTP-PASSWORD','starttls','587']
    report={key:True for key in ('database_matches','role_matches','active_schema_matches','search_path_contains_expected','expected_schema_exists','schema_usage','schema_create')}
    report.update(non_system_relation_count=0,non_system_sequence_count=0,non_system_function_count=0)
    with patch.dict('os.environ',{'PGSERVICE':'PRIVATE-STALE'},clear=True),patch('getpass.getpass',side_effect=inputs),patch('psycopg.connect'),patch('scripts.migrate_release_interactive.check',return_value=report):
        env=prepare()
    assert env['APP_ENV']=='production' and env['OLUMIRA_DB_DIAGNOSTIC']=='0'
    assert env['MIGRATION_DATABASE_URL']==url and 'PGSERVICE' not in env
    assert env['SMTP_PASSWORD']=='PRIVATE-SMTP-PASSWORD'
    assert 'PRIVATE-' not in capsys.readouterr().out
