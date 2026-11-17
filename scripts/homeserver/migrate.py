"""Apply the existing ledger migration to this project's isolated database."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine
from backend.account_migration import upgrade
from backend.database import normalize_database_url


def main():
    parser = argparse.ArgumentParser(description="Back up first; stop web before upgrading.")
    parser.add_argument("--apply", action="store_true", required=True)
    parser.parse_args()
    engine = create_engine(
        normalize_database_url(os.environ["DATABASE_URL"]),
        connect_args={"connect_timeout": 10},
    )
    try:
        print(upgrade(engine, os.environ["SMARTSPEND_PASSWORD_HASH"]))
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Migration stopped:", type(error).__name__, file=sys.stderr)
        raise SystemExit(1)
