"""Copy a consistent local snapshot to an EMPTY configured cloud database.

Default is read-only preflight. Use --apply after closing the local app.
No deletes/merges. All remote schema/data changes commit in one transaction.
"""
import argparse
import hashlib
import json
import socket
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Integer, create_engine, inspect, select, func, text
from backend import database, models, finance_models
from backend.finance_api import initialize_finance
from backend.finance_models import Preference, normalize_search
from prepare_cloud import OUTPUT


def transfer(source_engine, target_engine, fingerprint):
    tables = [t for t in database.Base.metadata.sorted_tables if t.name != 'spend_access_sessions']
    existing_source = set(inspect(source_engine).get_table_names())
    counts = {}
    with source_engine.connect() as source, target_engine.begin() as target:
        existing_target = set(inspect(target).get_table_names())
        if Preference.__tablename__ in existing_target:
            marker = target.execute(select(Preference.value).where(Preference.key == 'cloud_import_fingerprint')).scalar_one_or_none()
            if marker == fingerprint:
                return {'already_imported': True}
        for table in tables:
            if table.name in existing_target and target.execute(select(func.count()).select_from(table)).scalar_one():
                raise ValueError('Cloud đã có dữ liệu. Dừng để tránh ghi trùng hoặc ghi đè.')
        database.Base.metadata.create_all(target)
        if target_engine.dialect.name == 'postgresql':
            for name in ('plans', 'plan_items'):
                target.exec_driver_sql(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
        for table in tables:
            if table.name not in existing_source:
                continue
            columns = {c['name'] for c in inspect(source).get_columns(table.name)}
            query = select(*(column for column in table.c if column.name in columns))
            rows = [dict(row) for row in source.execute(query).mappings()]
            for row in rows:
                for key, value in row.items():
                    if isinstance(value, datetime) and value.tzinfo is None:
                        row[key] = value.replace(tzinfo=timezone.utc)
                if table.name == 'spend_transactions':
                    row['search_title'] = normalize_search(row['title'])
            if rows:
                target.execute(table.insert(), rows)
            counts[table.name] = len(rows)
            if target_engine.dialect.name == 'postgresql':
                primary = list(table.primary_key.columns)
                if len(primary) == 1 and isinstance(primary[0].type, Integer):
                    key = primary[0]
                    maximum = target.execute(select(func.max(key))).scalar_one()
                    target.execute(text('SELECT setval(pg_get_serial_sequence(:table_name, :column_name), :maximum, :has_rows)'),
                                   {'table_name': table.name, 'column_name': key.name, 'maximum': max(1, maximum or 1), 'has_rows': maximum is not None})
        target.execute(Preference.__table__.insert().values(key='cloud_import_fingerprint', value=fingerprint))
    return {'imported': counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    original = database.BASE_DIR / 'smartspend_local.db'
    if not original.exists():
        raise ValueError('Không có dữ liệu SQLite để chuyển')
    target_url = database.normalize_database_url(database.load_config().get('database_url', ''))
    target = create_engine(target_url, connect_args={'connect_timeout': 10}, pool_pre_ping=True)
    source = create_engine(f'sqlite:///{original.as_posix()}')
    try:
        with target.connect() as conn:
            conn.execute(text('SELECT 1'))
            target_tables = set(inspect(conn).get_table_names())
        with source.connect() as conn:
            source_tables = set(inspect(conn).get_table_names())
            counts = {table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
                      for table in database.Base.metadata.sorted_tables if table.name in source_tables}
        print(json.dumps({'local_counts': counts, 'cloud_schema_present': bool(target_tables & set(database.Base.metadata.tables)), 'apply': args.apply}, ensure_ascii=False))
        if not args.apply:
            return
        try:
            with socket.create_connection(('127.0.0.1', 8000), timeout=0.3):
                raise ValueError('Hãy đóng app trên máy tính trước khi chuyển dữ liệu')
        except OSError:
            pass
        OUTPUT.mkdir(parents=True, exist_ok=True)
        snapshot = OUTPUT / ('local-data-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.db')
        source.dispose()
        with closing(sqlite3.connect(original.as_uri() + '?mode=ro', uri=True)) as original_db, closing(sqlite3.connect(snapshot)) as backup:
            original_db.backup(backup)
        fingerprint = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        snapshot_engine = create_engine(f'sqlite:///{snapshot.as_posix()}')
        try:
            report = transfer(snapshot_engine, target, fingerprint)
        finally:
            snapshot_engine.dispose()
        initialize_finance(target)
        (OUTPUT / 'migration-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Da chuyen du lieu. Bao cao: output/deployment/migration-report.json')
    finally:
        source.dispose()
        target.dispose()


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print(str(error))
        raise SystemExit(1)
    except Exception as error:
        print('Chua chuyen duoc du lieu:', type(error).__name__, '(khong thay doi du lieu SQLite goc)')
        raise SystemExit(1)
