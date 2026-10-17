from pathlib import Path
import click
from flask_migrate import stamp
from sqlalchemy import inspect
from .extensions import db
from .models import Owner, Routine, Observation, RoutineCompletion
from services.data_transfer import backup_sqlite, read_snapshot, transfer_sqlite, LEGACY_COLUMNS


def register_commands(app):
    @app.cli.command('backup-sqlite')
    @click.option('--source', required=True, type=click.Path(exists=True, dir_okay=False))
    @click.option('--backup', required=True, type=click.Path(dir_okay=False))
    def backup_command(source, backup):
        """Create an exclusive SQLite recovery snapshot without changing the source."""
        try:
            backup_sqlite(source, backup)
            counts = {name: len(rows) for name, rows in read_snapshot(backup).items()}
        except Exception:
            raise click.ClickException('Backup or source validation failed; inspect the source locally. No records were logged.') from None
        click.echo(f'Backup verified. Counts: {counts}')

    @app.cli.command('transfer-sqlite')
    @click.option('--source', required=True, type=click.Path(exists=True, dir_okay=False))
    @click.option('--backup', required=True, type=click.Path(dir_okay=False))
    def transfer_command(source, backup):
        """Import SQLite into the configured EMPTY migrated destination."""
        try:
            counts = transfer_sqlite(source, backup)
        except Exception:
            raise click.ClickException('Transfer refused or failed. Destination transaction was rolled back. Verify schema, backup, and connection configuration locally.') from None
        click.echo(f'Transfer verified. Counts: {counts}')

    @app.cli.command('adopt-legacy-sqlite')
    @click.option('--backup', required=True, type=click.Path(dir_okay=False))
    def adopt_command(backup):
        """Back up and stamp a matching legacy SQLite baseline; never change records."""
        try:
            if db.engine.dialect.name != 'sqlite' or not db.engine.url.database or db.engine.url.database == ':memory:':
                raise ValueError('Only file-based SQLite can be adopted')
            inspector = inspect(db.engine)
            if set(inspector.get_table_names()) != {'owners', 'routines', 'observations', 'routine_completions'}:
                raise ValueError('Unexpected schema; adoption refused')
            backup_sqlite(db.engine.url.database, backup)
            read_snapshot(backup)
            for model in (Owner, Routine, Observation, RoutineCompletion):
                table = model.__table__
                columns = inspector.get_columns(table.name)
                if {c['name'] for c in columns} != set(LEGACY_COLUMNS[table.name]):
                    raise ValueError('Unexpected columns')
                if set(inspector.get_pk_constraint(table.name)['constrained_columns']) != {c.name for c in table.primary_key}:
                    raise ValueError('Unexpected primary key')
                for column in columns:
                    expected = table.columns[column['name']]
                    if type(column['type']).__name__.lower() != type(expected.type).__name__.lower():
                        raise ValueError('Unexpected column type')
                    if not expected.primary_key and column['nullable'] != expected.nullable:
                        raise ValueError('Unexpected nullability')
                expected_indexes = {(index.name, tuple(c.name for c in index.columns)) for index in table.indexes if tuple(c.name for c in index.columns) != ('workspace_id',)}
                actual_indexes = {(index['name'], tuple(index['column_names'])) for index in inspector.get_indexes(table.name)}
                if expected_indexes != actual_indexes:
                    raise ValueError('Unexpected indexes')
            fks = inspector.get_foreign_keys('routine_completions')
            if len(fks) != 1 or fks[0]['referred_table'] != 'routines' or fks[0]['constrained_columns'] != ['routine_id'] or fks[0]['referred_columns'] != ['id'] or fks[0].get('options', {}).get('ondelete', '').upper() != 'CASCADE':
                raise ValueError('Unexpected completion relationship')
            stamp(revision='0001', directory=str(Path(app.root_path).parent / 'migrations'))
        except Exception:
            raise click.ClickException('Legacy adoption refused or failed. Verify the supported schema and backup locally; no records were changed.') from None
        click.echo('Backup verified; legacy schema stamped at 0001. Records preserved.')
