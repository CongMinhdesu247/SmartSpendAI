"""Transactional local-ledger upgrade, with a consistent SQLite backup first."""
import sqlite3
from contextlib import closing
from pathlib import Path
from sqlalchemy import MetaData, inspect
from sqlalchemy.schema import CreateTable, CreateIndex
from backend.database import Base
from backend.tenancy import OWNER_ID


def upgrade_local(engine):
    from backend.account_migration import ledger_tables
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    names = [name for name in ledger_tables() + ["spend_access_sessions"] if name in existing]
    if not any("user_id" not in {c["name"] for c in inspector.get_columns(name)} for name in names):
        return
    source_path = engine.url.database
    if source_path and source_path != ":memory:":
        path = Path(source_path)
        backup = path.with_name(path.stem + ".before_private_ledgers.db")
        if not backup.exists():
            with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(backup)) as target:
                source.backup(target)
    # Temporary tables retain FK references to final table names. Disable FK checks
    # only for the atomic table replacement, then verify before the commit.
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(metadata)
    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN IMMEDIATE")
        for name in names:
            table = Base.metadata.tables[name]
            temporary = table.to_metadata(metadata, name="_private_upgrade_" + name)
            cursor.execute(str(CreateTable(temporary).compile(dialect=engine.dialect)))
            previous = {r[1] for r in cursor.execute(f'PRAGMA table_info("{name}")').fetchall()}
            columns = [c.name for c in table.columns]
            selected = [f'"{c}"' if c in previous else "'" + OWNER_ID + "'" for c in columns]
            cursor.execute(f'INSERT INTO "{temporary.name}" (' + ','.join(f'"{c}"' for c in columns) + ') SELECT ' + ','.join(selected) + f' FROM "{name}"')
        for name in names:
            cursor.execute(f'DROP TABLE "{name}"')
        for name in names:
            cursor.execute(f'ALTER TABLE "_private_upgrade_{name}" RENAME TO "{name}"')
            for index in Base.metadata.tables[name].indexes:
                cursor.execute(str(CreateIndex(index).compile(dialect=engine.dialect)))
        if cursor.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("SQLite ownership upgrade failed foreign-key validation")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.cursor().execute("PRAGMA foreign_keys=ON")
        connection.close()
