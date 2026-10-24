"""Manual encrypted backup wizard; no credentials in argv, output or source files."""
import getpass
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cryptography.fernet import Fernet
from scripts.postgres_preflight import parameters


def backup_environment(url, key, tool_directory):
    params=parameters(url)
    allowed={'host','port','dbname','user','password','sslmode','sslrootcert','connect_timeout',
             'ssl_min_protocol_version','ssl_max_protocol_version'}
    if set(params)-allowed or not all(params.get(k) for k in ('host','dbname','user','password')):
        raise ValueError('Unsupported or incomplete backup connection settings')
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
    mapping={'host':'PGHOST','port':'PGPORT','dbname':'PGDATABASE','user':'PGUSER',
             'password':'PGPASSWORD','sslmode':'PGSSLMODE','sslrootcert':'PGSSLROOTCERT',
             'connect_timeout':'PGCONNECT_TIMEOUT','ssl_min_protocol_version':'PGSSLMINPROTOCOLVERSION',
             'ssl_max_protocol_version':'PGSSLMAXPROTOCOLVERSION'}
    env.update({mapping[k]:str(v) for k,v in params.items() if v is not None})
    env['BACKUP_ENCRYPTION_KEY']=key.decode('ascii')
    env['PATH']=str(tool_directory)+os.pathsep+env.get('PATH','')
    return env


def main():
    if not sys.stdin.isatty():
        print('Run this command in an interactive terminal; do not pipe credentials.')
        return 1
    try:
        tool=next((p for p in (Path('/usr/local/opt/libpq/bin/pg_dump'),Path('/opt/homebrew/opt/libpq/bin/pg_dump')) if p.is_file()),None)
        if tool is None:
            found=shutil.which('pg_dump')
            if not found:raise ValueError('PostgreSQL tools unavailable')
            tool=Path(found)
        url=getpass.getpass('External database URL with Mac-compatible verified TLS (hidden): ')
        key=Fernet.generate_key()
        env=backup_environment(url,key,tool.parent)
        identifier=secrets.token_hex(12)
        backup_dir=Path.home()/'.local/share/olumira-backups'
        key_dir=Path.home()/'.config/olumira-backup-keys'
        for directory in (backup_dir,key_dir):
            if directory.is_symlink():raise ValueError('Private directory required')
            directory.mkdir(mode=0o700,parents=True,exist_ok=True)
            directory.chmod(0o700)
        destination=backup_dir/(identifier+'.enc')
        keyfile=key_dir/(identifier+'.key')
        descriptor=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'wb') as handle:
            handle.write(key);handle.flush();os.fsync(handle.fileno())
        result=subprocess.run([sys.executable,str(ROOT/'scripts/encrypted_backup.py'),'--output',str(destination)],env=env)
        if result.returncode:
            print('Backup failed. No migration was run. Retained recovery-key file:',keyfile)
            return 1
        print('Encrypted backup:',destination)
        print('Recovery-key file (keep private):',keyfile)
        print('Store the key in your approved vault separately from the backup. A restore rehearsal is still required.')
        return 0
    except Exception:
        print('Backup preparation failed; no credentials logged and no migration run.')
        return 1


if __name__=='__main__':raise SystemExit(main())
