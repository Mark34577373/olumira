"""Manual read-only catalog check. No URLs, role/schema names or data are printed."""
import getpass
import json
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.engine import make_url
import psycopg

KNOWN = ('alembic_version', 'owners', 'users', 'family_workspaces',
         'workspace_memberships', 'audit_events', 'routines', 'routine_steps',
         'account_tokens', 'email_outbox', 'auth_sessions')


def parameters(url):
    parsed=make_url(url)
    if parsed.drivername not in {'postgres','postgresql','postgresql+psycopg'}:
        raise ValueError('PostgreSQL required')
    if parsed.query.get('sslmode')!='verify-full':
        raise ValueError('Verified TLS required')
    if not parsed.query.get('sslrootcert'):
        raise ValueError('Explicit trusted roots required')
    if any(isinstance(value,tuple) for value in parsed.query.values()):
        raise ValueError('Duplicate query options refused')
    if any(key in parsed.query for key in ('host','hostaddr','service','dbname','user','password')):
        raise ValueError('Conflicting identity options refused')
    return dict(parsed.query,host=parsed.host,port=parsed.port or 5432,
                dbname=parsed.database,user=parsed.username,password=parsed.password,
                connect_timeout=5)


def check(connection, expected_database, expected_role, expected_schema):
    with connection.transaction():
        connection.execute('SET TRANSACTION READ ONLY')
        connection.execute("SET LOCAL statement_timeout='10000'")
        connection.execute("SET LOCAL lock_timeout='3000'")
        identity=connection.execute('SELECT current_database(), current_user, current_schema(), current_schemas(false), current_setting(\'server_version_num\')::integer').fetchone()
        report=dict(database_matches=identity[0]==expected_database,
                    role_matches=identity[1]==expected_role,
                    active_schema_matches=identity[2]==expected_schema,
                    search_path_contains_expected=expected_schema in identity[3],
                    server_version_num=identity[4])
        # pg_catalog is deliberately used instead of privilege-filtered information_schema.
        rows=connection.execute("""SELECT n.nspname,c.relname,pg_table_is_visible(c.oid),
            has_schema_privilege(n.oid,'USAGE'),has_table_privilege(c.oid,'SELECT')
            FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind IN ('r','p','v','m','f')
            AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'""").fetchall()
        report['non_system_relation_count']=len(rows)
        report['non_system_sequence_count']=connection.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='S' AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'").fetchone()[0]
        report['non_system_function_count']=connection.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'").fetchone()[0]
        report['auth_relations']={name:dict(
            catalog_present=any(row[1]==name for row in rows),
            in_expected_schema=any(row[0]==expected_schema and row[1]==name for row in rows),
            visible=any(row[1]==name and row[2] for row in rows),
            selectable=any(row[0]==expected_schema and row[1]==name and row[3] and row[4] for row in rows)
        ) for name in KNOWN}
        report['expected_schema_exists']=connection.execute('SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=%s)',(expected_schema,)).fetchone()[0]
        if report['expected_schema_exists']:
            report['schema_usage'],report['schema_create']=connection.execute('SELECT has_schema_privilege(%s,\'USAGE\'),has_schema_privilege(%s,\'CREATE\')',(expected_schema,expected_schema)).fetchone()
        return report


def main():
    if not sys.stdin.isatty():
        print('Interactive terminal required; credentials must not be piped or echoed.')
        return 1
    try:
        url=getpass.getpass('External database URL with verified TLS (hidden): ')
        database=getpass.getpass('Expected database name from Render (hidden): ')
        role=getpass.getpass('Expected role name (hidden): ')
        schema=getpass.getpass('Expected schema name (hidden; normally public): ')
        if not all((database,role,schema)):
            raise ValueError('Expected identity is required')
        with psycopg.connect(**parameters(url)) as connection:
            print(json.dumps(check(connection,database,role,schema),sort_keys=True))
    except Exception as error:
        original=getattr(error,'orig',None) or error
        state=getattr(original,'sqlstate',None)
        if not isinstance(state,str) or not re.fullmatch(r'[A-Z0-9]{5}',state):state='unavailable'
        print(json.dumps(dict(status='preflight_failed',error_class=type(error).__name__,sqlstate=state)))
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
