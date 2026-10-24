"""Manual release wizard. Readonly preflight; migration requires explicit confirmation."""
import getpass
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory
from olumira.config import configuration
from scripts.postgres_preflight import parameters,check


def prepare():
    config=Config();config.set_main_option('script_location',str(ROOT/'migrations'))
    if ScriptDirectory.from_config(config).get_heads()!=['0022']:
        raise ValueError('Release head changed; review required')
    url=getpass.getpass('Migration External Database URL with Mac CA path (hidden): ')
    database=getpass.getpass('Expected database name (hidden): ')
    role=getpass.getpass('Expected migration role name (hidden): ')
    schema=getpass.getpass('Expected schema (hidden; enter public): ')
    if not all((database,role)) or schema!='public':
        raise ValueError('Reviewed public-schema identity required')
    with psycopg.connect(**parameters(url)) as connection:
        report=check(connection,database,role,schema)
    gates=('database_matches','role_matches','active_schema_matches',
           'search_path_contains_expected','expected_schema_exists','schema_usage','schema_create')
    if not all(report.get(key) for key in gates):
        raise ValueError('Target identity/schema/permissions mismatch')
    if any(report[key] for key in ('non_system_relation_count','non_system_sequence_count','non_system_function_count')):
        raise ValueError('Nonempty database requires separate review')
    print('Read-only preflight passed: expected identity, public schema and CREATE permission; no user relations found.')
    print('Copy these existing settings from Render Environment. Values remain hidden; nothing is saved to a file.')
    settings=dict(APP_ENV='production',DATABASE_URL=url,OLUMIRA_DB_DIAGNOSTIC=False,
                  PUBLIC_APP_URL='https://olumira.onrender.com',MAIL_BACKEND='smtp',
                  TRUSTED_PROXY_HOPS=0)
    for key in ('SECRET_KEY','MAIL_ENCRYPTION_KEY','RATELIMIT_STORAGE_URI','MAIL_FROM',
                'SMTP_HOST','SMTP_USERNAME','SMTP_PASSWORD'):
        settings[key]=getpass.getpass(key+' from Render (hidden): ')
    settings['SMTP_SECURITY']=getpass.getpass('SMTP_SECURITY from Render (starttls or ssl; hidden): ')
    settings['SMTP_PORT']=int(getpass.getpass('SMTP_PORT from Render (587 or 465; hidden): '))
    configuration(settings)  # Validate only; no engine, writes or SMTP delivery.
    env={key:value for key,value in os.environ.items() if not key.startswith('PG')}
    env.update({key:str(value) for key,value in settings.items()
                if key not in {'DATABASE_URL','OLUMIRA_DB_DIAGNOSTIC'}})
    env['MIGRATION_DATABASE_URL']=url
    env['OLUMIRA_DB_DIAGNOSTIC']='0'
    env.pop('DATABASE_URL',None)
    return env


def main():
    if not sys.stdin.isatty():
        print('Interactive terminal required. Do not pipe secrets.')
        return 1
    try:
        env=prepare()
    except Exception:
        print('Preparation failed. No migrations run. Check target, permissions and copied settings; private error text suppressed.')
        return 1
    print('Configuration validated. No migration has run.')
    print('This will create the application schema through revision 0022 using the existing release runner.')
    print('Proceed only with the verified backup/restore rehearsal and intended migration role. Otherwise press Enter to cancel.')
    if input('Type MIGRATE 0022 to execute, or press Enter to cancel: ').strip()!='MIGRATE 0022':
        print('Cancelled. No migrations run; entered settings were not saved.')
        return 0
    try:
        result=subprocess.run([sys.executable,str(ROOT/'scripts/migrate_release.py')],env=env)
    except Exception:
        print('Release runner could not start. No private details logged.')
        return 1
    if result.returncode:
        print('Migration failed. Keep writers paused; inspect state before any retry.')
        return 1
    print('Migration runner completed. Verify runtime grants, revision, readiness and fictional authentication before reopening traffic.')
    return 0


if __name__=='__main__':raise SystemExit(main())
