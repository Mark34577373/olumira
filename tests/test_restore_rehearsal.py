"""Restore rehearsal is constrained to a new local cluster and private socket."""
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.fernet import Fernet
from scripts.rehearse_postgres_restore import rehearse,clean_environment


def test_rehearsal_cannot_inherit_production_connection_or_overwrite_backup(tmp_path,capsys):
    key=Fernet.generate_key();keyfile=tmp_path/'key';keyfile.write_bytes(key)
    backup=tmp_path/'backup';original=Fernet(key).encrypt(b'PGDMPfictional-archive');backup.write_bytes(original)
    scratch=tmp_path/'scratch';scratch.mkdir(mode=0o700)
    with patch('os.environ',{'PGHOST':'PRIVATE-RENDER','PGPASSWORD':'PRIVATE-PASSWORD','PATH':'/usr/bin'}),patch('pathlib.Path.is_file',return_value=True),patch('tempfile.mkdtemp',return_value=str(scratch)),patch('subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=b'0\n')) as run:
        assert rehearse(backup,keyfile)==0
    calls=run.call_args_list
    assert all('PGHOST' not in call.kwargs['env'] and 'PGPASSWORD' not in call.kwargs['env'] for call in calls)
    startup=next(call.args[0] for call in calls if 'start' in call.args[0])
    assert any("listen_addresses=''" in arg for arg in startup)
    restore=next(call for call in calls if call.args[0][0].endswith('/pg_restore'))
    assert '--exit-on-error' in restore.args[0] and '--no-owner' in restore.args[0]
    assert str(scratch/'socket') in restore.args[0]
    assert backup.read_bytes()==original and keyfile.read_bytes()==key
    assert not scratch.exists()
    assert 'PRIVATE-' not in capsys.readouterr().out


def test_environment_strips_service_and_password_defaults():
    with patch('os.environ',{'PGSERVICE':'private','PGHOSTADDR':'private','PATH':'/bin'}):
        assert clean_environment()=={'PATH':'/bin','LC_ALL':'C'}
