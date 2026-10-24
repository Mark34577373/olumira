"""Backup wrapper preserves TLS and keeps secrets out of command arguments."""
from unittest.mock import patch
import pytest
from cryptography.fernet import Fernet
from scripts.backup_postgres_interactive import backup_environment,main


def test_private_environment_keeps_tls_and_clears_conflicting_pg_defaults():
    with patch.dict('os.environ',{'PGSERVICE':'PRIVATE-SERVICE','PGHOSTADDR':'PRIVATE-ADDRESS'}):
        env=backup_environment('postgresql://user:PRIVATE-PASSWORD@PRIVATE-HOST/db?sslmode=verify-full&sslrootcert=/etc/ssl/cert.pem',Fernet.generate_key(),'/private/tools')
    assert env['PGSSLMODE']=='verify-full' and env['PGSSLROOTCERT']=='/etc/ssl/cert.pem'
    assert env['PGPASSWORD']=='PRIVATE-PASSWORD' and env['PGHOST']=='PRIVATE-HOST'
    assert 'PGSERVICE' not in env and 'PGHOSTADDR' not in env
    assert env['PATH'].startswith('/private/tools:')


def test_weak_tls_is_rejected():
    with pytest.raises(ValueError):backup_environment('postgresql://user:secret@host/db?sslmode=require&sslrootcert=system',Fernet.generate_key(),'/tools')


def test_backup_command_has_no_credentials_and_uses_private_files(tmp_path,capsys):
    url='postgresql://PRIVATE-USER:PRIVATE-PASSWORD@PRIVATE-HOST/db?sslmode=verify-full&sslrootcert=/etc/ssl/cert.pem'
    with patch('sys.stdin.isatty',return_value=True),patch('pathlib.Path.home',return_value=tmp_path),patch('pathlib.Path.is_file',return_value=True),patch('getpass.getpass',return_value=url),patch('subprocess.run') as run:
        run.return_value.returncode=0
        assert main()==0
    args=run.call_args.args[0]
    assert not any('PRIVATE-' in str(arg) for arg in args)
    keyfiles=list((tmp_path/'.config/olumira-backup-keys').glob('*.key'))
    assert len(keyfiles)==1 and keyfiles[0].stat().st_mode & 0o777==0o600
    assert 'PRIVATE-' not in capsys.readouterr().out
