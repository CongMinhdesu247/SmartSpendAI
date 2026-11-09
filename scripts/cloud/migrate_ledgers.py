"""Inspect by default; --apply backs up public data before the transactional upgrade."""

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from backend.database import normalize_database_url
from backend.account_migration import upgrade, ledger_tables, VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--env-file", default=".env.cloud")
    parser.add_argument(
        "--pg-dump",
        default=shutil.which("pg_dump") or "C:/Program Files/PostgreSQL/18/bin/pg_dump.exe",
    )
    args = parser.parse_args()
    env = dict(os.environ)
    for line in Path(args.env_file).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    url = make_url(normalize_database_url(env["DATABASE_URL"]))
    engine = create_engine(url, connect_args={"connect_timeout": 10})
    try:
        with engine.connect() as conn:
            existing = set(inspect(conn).get_table_names())
            counts = {
                name: conn.execute(text(f'SELECT count(*) FROM "{name}"')).scalar()
                for name in ledger_tables()
                if name in existing
            }
            applied = "spend_schema_versions" in existing and bool(
                conn.execute(
                    text("SELECT 1 FROM spend_schema_versions WHERE version=:v"), {"v": VERSION}
                ).scalar()
            )
        report = {
            "mode": "apply" if args.apply else "inspect",
            "version": VERSION,
            "already_applied": applied,
            "counts_before": counts,
        }
        if args.apply and not applied:
            output = Path("output/deployment")
            output.mkdir(parents=True, exist_ok=True)
            backup = output / (
                "before-private-ledgers-"
                + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                + ".dump"
            )
            # Credentials stay in the child's environment, never command arguments or output.
            pg_env = dict(
                os.environ,
                PGPASSWORD=url.password or "",
                PGSSLMODE=url.query.get("sslmode", "require"),
            )
            command = [
                args.pg_dump,
                "--host",
                url.host,
                "--port",
                str(url.port or 5432),
                "--username",
                url.username,
                "--dbname",
                url.database,
                "--format=custom",
                "--schema=public",
                "--no-owner",
                "--no-acl",
                "--file",
                str(backup),
            ]
            result = subprocess.run(command, env=pg_env, capture_output=True)
            if result.returncode or not backup.exists() or backup.stat().st_size == 0:
                raise RuntimeError("Backup failed; migration was not applied")
            report["backup"] = str(backup)
            report["migration"] = upgrade(engine, env["SMARTSPEND_PASSWORD_HASH"])
            with engine.connect() as conn:
                report["counts_after"] = {
                    name: conn.execute(text(f'SELECT count(*) FROM "{name}"')).scalar()
                    for name in counts
                }
            if report["counts_after"] != counts:
                raise RuntimeError(
                    "Row counts changed; inspect the backup and migration report before deploying"
                )
        print(json.dumps(report, indent=2))
        if args.apply:
            Path("output/deployment").mkdir(parents=True, exist_ok=True)
            Path("output/deployment/private-ledger-migration.json").write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # SQLAlchemy exceptions can embed URLs, parameters and hashes; never print them.
        print(
            "Migration stopped ("
            + type(error).__name__
            + "). No credentials were printed. Check configuration and backup availability."
        )
        raise SystemExit(1)
