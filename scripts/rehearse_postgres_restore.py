"""Restore an encrypted archive into a fresh private local cluster, never Render."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from cryptography.fernet import Fernet


def clean_environment():
    env={key:value for key,value in os.environ.items() if not key.startswith('PG')}
    env['LC_ALL']='C'
    return env


def rehearse(backup, keyfile):
    binary=next((path for path in (Path('/usr/local/opt/postgresql@18/bin'),Path('/opt/homebrew/opt/postgresql@18/bin')) if (path/'postgres').is_file()),None)
    if binary is None:
        print('PostgreSQL 18 server tools not found. No database was changed.')
        return 1
    # Authenticate before starting a server; decrypted data stays in memory.
    payload=Fernet(keyfile.read_bytes()).decrypt(backup.read_bytes())
    if not payload.startswith(b'PGDMP'):
        raise ValueError('Invalid archive')
    env=clean_environment()
    scratch=Path(tempfile.mkdtemp(prefix='olumira-restore-',dir='/private/tmp'))
    data=scratch/'data';socket=scratch/'socket';socket.mkdir(mode=0o700)
    started=False
    def command(name,*args,**kwargs):
        return subprocess.run([str(binary/name),*map(str,args)],env=env,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                              check=True,timeout=180,**kwargs)
    try:
        command('initdb','-D',data,'--username=olumira_restore','--encoding=UTF8',
                '--locale=C','--auth-local=trust','--auth-host=reject')
        # Socket directory inherits a private 0700 root; TCP is entirely disabled.
        options=f"-c listen_addresses='' -c unix_socket_directories={socket} -c shared_buffers=16MB -c max_connections=10 -p 5432"
        # Mark possibly started before waiting, so any timeout still attempts stop.
        started=True
        command('pg_ctl','-D',data,'-l',scratch/'server.log','-o',options,'-w','start')
        connection=('--host',socket,'--port','5432','--username','olumira_restore')
        command('createdb',*connection,'olumira_recovery_test')
        command('pg_restore',*connection,'--dbname','olumira_recovery_test',
                '--no-owner','--no-privileges','--exit-on-error',input=payload)
        query="SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind IN ('r','p') AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'"
        result=subprocess.run([str(binary/'psql'),*map(str,connection),'--dbname','olumira_recovery_test','-X','-A','-t','-c',query],
                              env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              check=True,timeout=30)
        count=int(result.stdout.strip())
        print(f'Local restore succeeded. Non-system tables restored: {count}.')
        print('Render was not contacted. No migration was run.')
        return 0
    finally:
        safe_to_remove=not started
        if started:
            try:
                command('pg_ctl','-D',data,'-m','fast','-w','stop')
                safe_to_remove=True
            except Exception:
                # If startup failed, confirm no server remains before cleanup.
                status=subprocess.run([str(binary/'pg_ctl'),'-D',str(data),'status'],env=env,
                                      stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
                safe_to_remove=status.returncode==3
        if safe_to_remove:
            shutil.rmtree(scratch)
            print('Temporary local cluster removed. Original backup and key preserved.')
        else:
            print('Temporary cluster retained for operator inspection:',scratch)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--key',type=Path,required=True)
    args=parser.parse_args()
    try:
        return rehearse(args.backup,args.key)
    except Exception:
        print('Local restore rehearsal failed. No Render connection or migration was attempted; private error details suppressed.')
        return 1


if __name__=='__main__':raise SystemExit(main())
