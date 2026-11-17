"""Read-only database check, useful after restoring into an isolated project."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, text
from backend.account_migration import require_ready, ledger_tables
from backend.database import normalize_database_url


def main():
    engine = create_engine(normalize_database_url(os.environ["DATABASE_URL"]))
    try:
        require_ready(engine)
        with engine.connect() as conn:
            for name in ["spend_accounts", *ledger_tables()]:
                count = conn.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one()
                print(f"{name}: {count}")
            unsafe = conn.execute(
                text(
                    "SELECT rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb FROM pg_roles WHERE rolname=current_user"
                )
            ).scalar_one()
            if unsafe:
                raise RuntimeError("App login must not have administrative role flags")
        print("Database schema, app role and ledger access: OK")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Database check failed:", type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
