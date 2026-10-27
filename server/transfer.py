"""Transfer the modern SQLite pipeline to a fresh PostgreSQL database, without credentials."""
import argparse
import copy
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from sqlalchemy import func, insert, select, text, update

from server.db import ACTIVE, Database, control, metadata, queue, runs


EXCLUDED = {'pipeline_sessions', 'pipeline_login_limits', 'pipeline_workers'}
TABLES = [t for t in metadata.sorted_tables if t.name not in EXCLUDED]


def export_sqlite(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file() or output.exists():
        raise ValueError('Source must exist and output must be a new file')
    # SQLite's backup API includes committed WAL writes in a consistent snapshot.
    with tempfile.TemporaryDirectory() as temporary:
        snapshot = Path(temporary) / 'snapshot.db'
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as origin:
            with closing(sqlite3.connect(snapshot)) as target:
                origin.backup(target)
        db = Database('sqlite:///' + snapshot.as_posix())
        try:
            with db.engine.connect() as c:
                tables = {t.name: [dict(r) for r in c.execute(select(t)).mappings()] for t in TABLES}
        finally:
            db.engine.dispose()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as f:
        json.dump({'format': 'upwork-pipeline-v2', 'tables': tables}, f, ensure_ascii=False)
    output.chmod(0o600)
    return {name: len(rows) for name, rows in tables.items()}


def import_snapshot(db, source):
    payload = json.loads(Path(source).read_text(encoding='utf-8'))
    if payload.get('format') != 'upwork-pipeline-v2' or set(payload.get('tables', {})) != {t.name for t in TABLES}:
        raise ValueError('Unsupported or incomplete pipeline snapshot')
    values = copy.deepcopy(payload['tables'])
    controls = values['pipeline_control']
    if len(controls) != 1 or controls[0]['id'] != 1:
        raise ValueError('Snapshot must have exactly one control row')
    controls[0]['remote_control'] = 0
    # Start safely on the new host; the operator verifies profiles before resuming.
    controls[0]['settings'].update(enabled=False, deliver_to_chat=False, browser_windows_visible=False)
    for row in values['pipeline_runs']:
        if row['status'] in ACTIVE:
            row.update(status='paused', error='Moved to server; verify both browser logins, then resume.')
    for row in values['pipeline_queue']:
        if row['status'] == 'running':
            row.update(status='pending', worker='', retry_at=0)
    for row in values['pipeline_alerts']:
        if row['status'] == 'pending':
            row['status'] = 'cancelled'  # Do not send stale local alerts from the server.
    db.init()
    with db.engine.begin() as c:
        # This importer is deliberately for an empty target, never a merge/overwrite.
        for table in metadata.sorted_tables:
            if table.name not in ('pipeline_control', 'pipeline_schema_versions'):
                if c.execute(select(func.count()).select_from(table)).scalar_one():
                    raise ValueError('Target database is not empty; import cancelled')
        for table in TABLES:
            rows = values[table.name]
            if table.name in ('pipeline_control', 'pipeline_schema_versions'):
                c.execute(table.delete())
            for start in range(0, len(rows), 500):
                c.execute(insert(table), rows[start:start + 500])
        if db.engine.dialect.name == 'postgresql':
            schema = c.get_execution_options().get('schema_translate_map', {}).get(None, 'public')
            for table in TABLES:
                column = table.autoincrement_column
                if column is not None:
                    maximum = c.execute(select(func.max(column))).scalar_one()
                    c.execute(text('SELECT setval(pg_get_serial_sequence(:table_name, :column_name), :value, :called)'),
                              {'table_name': schema + '.' + table.name, 'column_name': column.name,
                               'value': maximum or 1, 'called': maximum is not None})
        counts = {t.name: c.execute(select(func.count()).select_from(t)).scalar_one() for t in TABLES}
        if counts != {name: len(rows) for name, rows in values.items()}:
            raise ValueError('Row count verification failed; import rolled back')
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export')
    export.add_argument('--source', required=True)
    export.add_argument('--output', required=True)
    migrate = commands.add_parser('import')
    migrate.add_argument('--input', required=True)
    args = parser.parse_args()
    if args.command == 'export':
        counts = export_sqlite(args.source, args.output)
    else:
        from server.config import Settings
        settings = Settings()
        db = Database(settings.database_url)
        try:
            if db.engine.dialect.name != 'postgresql':
                raise ValueError('Server import requires PostgreSQL, not the local SQLite database')
            counts = import_snapshot(db, args.input)
        finally:
            db.engine.dispose()
    print(json.dumps(counts, sort_keys=True))


if __name__ == '__main__':
    main()
