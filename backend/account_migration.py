"""Explicit, transactional PostgreSQL upgrade; never run as an app startup side effect."""

from sqlalchemy import inspect, text
from backend.database import Base
from backend.tenancy import OWNER_ID, RUNTIME_ROLE, LedgerOwned

VERSION = "private-ledgers-v1"


def ledger_tables():
    from backend import models, finance_models  # noqa: F401

    return sorted(
        m.local_table.name for m in Base.registry.mappers if issubclass(m.class_, LedgerOwned)
    )


def upgrade(engine, owner_password_hash):
    if engine.dialect.name != "postgresql":
        raise ValueError("Cloud migration requires PostgreSQL")
    if not owner_password_hash.startswith("$argon2id$"):
        raise ValueError("Owner password hash is required")
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(73928341)"))
        conn.execute(text("SET LOCAL lock_timeout = '10s'"))
        conn.execute(
            text("CREATE TABLE IF NOT EXISTS spend_schema_versions (version text PRIMARY KEY)")
        )
        conn.execute(text("ALTER TABLE spend_schema_versions ENABLE ROW LEVEL SECURITY"))
        if conn.execute(
            text("SELECT 1 FROM spend_schema_versions WHERE version=:v"), {"v": VERSION}
        ).scalar():
            return {"status": "already_applied", "version": VERSION}
        # create_all only creates missing tables; existing rows/IDs remain untouched.
        Base.metadata.create_all(conn)
        tables = ledger_tables()
        for name in tables + ["spend_access_sessions"]:
            columns = {c["name"] for c in inspect(conn).get_columns(name)}
            if "user_id" not in columns:
                conn.execute(
                    text(
                        f'ALTER TABLE "{name}" ADD COLUMN user_id varchar(36) NOT NULL DEFAULT :owner'
                    ),
                    {"owner": OWNER_ID},
                )
            conn.execute(
                text(f'CREATE INDEX IF NOT EXISTS "ix_{name}_user_id" ON "{name}" (user_id)')
            )
        # Replace global natural keys / idempotency keys with per-person keys.
        for name, columns in (
            ("spend_categories", ["name"]),
            ("spend_transactions", ["client_id"]),
            ("spend_contributions", ["client_id"]),
        ):
            for unique in inspect(conn).get_unique_constraints(name):
                if unique["column_names"] == columns:
                    constraint = conn.dialect.identifier_preparer.quote(unique["name"])
                    conn.execute(text(f'ALTER TABLE "{name}" DROP CONSTRAINT {constraint}'))
            conn.execute(
                text(
                    f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{name}_user_key" ON "{name}" (user_id, "{columns[0]}")'
                )
            )
        for name in ("spend_preferences", "spend_budgets"):
            pk = inspect(conn).get_pk_constraint(name)
            if pk["constrained_columns"] != ["user_id", "key"]:
                constraint = conn.dialect.identifier_preparer.quote(pk["name"])
                conn.execute(text(f'ALTER TABLE "{name}" DROP CONSTRAINT {constraint}'))
                conn.execute(text(f'ALTER TABLE "{name}" ADD PRIMARY KEY (user_id, key)'))
        conn.execute(
            text(
                "INSERT INTO spend_accounts (id,username,password_hash,active,created_at) VALUES (:id,'chuso',:hash,true,CURRENT_TIMESTAMP) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": OWNER_ID, "hash": owner_password_hash},
        )
        # Old cookies were issued without a named account; require a fresh login.
        conn.execute(text("DELETE FROM spend_access_sessions"))
        conn.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='smartspend_ledger') THEN CREATE ROLE smartspend_ledger NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS; END IF; END $$"
            )
        )
        unsafe_role = conn.execute(
            text(
                "SELECT rolsuper OR rolbypassrls OR rolcanlogin OR rolcreaterole OR rolcreatedb FROM pg_roles WHERE rolname='smartspend_ledger'"
            )
        ).scalar()
        if unsafe_role:
            raise RuntimeError("The ledger runtime role must be unprivileged and NOLOGIN")
        conn.execute(text("GRANT smartspend_ledger TO CURRENT_USER"))
        conn.execute(text("GRANT USAGE ON SCHEMA public TO smartspend_ledger"))
        for name in tables:
            conn.execute(text(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY'))
            conn.execute(text(f'REVOKE ALL ON "{name}" FROM PUBLIC, anon, authenticated'))
            conn.execute(text(f'GRANT SELECT,INSERT,UPDATE,DELETE ON "{name}" TO {RUNTIME_ROLE}'))
            conn.execute(
                text(
                    f"CREATE POLICY private_ledger ON \"{name}\" TO {RUNTIME_ROLE} USING (user_id = current_setting('app.user_id', true)) WITH CHECK (user_id = current_setting('app.user_id', true))"
                )
            )
            if "id" in Base.metadata.tables[name].c:
                seq = conn.execute(
                    text("SELECT pg_get_serial_sequence(:name,'id')"), {"name": name}
                ).scalar()
                if seq:
                    seq_name = ".".join(
                        conn.dialect.identifier_preparer.quote(p) for p in seq.split(".")
                    )
                    conn.execute(
                        text(f"GRANT USAGE,SELECT ON SEQUENCE {seq_name} TO {RUNTIME_ROLE}")
                    )
                    conn.execute(
                        text(
                            f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{name}_owner_id" ON "{name}" (user_id,id)'
                        )
                    )
        # Composite FKs also prevent cross-person links in raw SQL, beyond API checks.
        links = [
            ("plan_items", "plan_id", "plans", False),
            ("spend_recurring", "category_id", "spend_categories", False),
            ("spend_transactions", "category_id", "spend_categories", False),
            ("spend_transactions", "source_item_id", "plan_items", True),
            ("spend_transactions", "recurring_id", "spend_recurring", False),
            ("spend_budgets", "category_id", "spend_categories", False),
            ("spend_contributions", "goal_id", "spend_goals", False),
            ("spend_plan_archive", "restored_plan_id", "plans", True),
        ]
        for name, column, target, _set_null in links:
            # Keep existing single-column FK delete actions and add ownership validation.
            conn.execute(
                text(
                    f'ALTER TABLE "{name}" ADD CONSTRAINT "fk_{name}_{column}_owner" FOREIGN KEY (user_id,"{column}") REFERENCES "{target}" (user_id,id) DEFERRABLE INITIALLY DEFERRED'
                )
            )
        for name in ("spend_accounts", "spend_access_sessions", "spend_schema_versions"):
            conn.execute(text(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY'))
            conn.execute(
                text(f'REVOKE ALL ON "{name}" FROM PUBLIC, anon, authenticated, {RUNTIME_ROLE}')
            )
        conn.execute(text("INSERT INTO spend_schema_versions(version) VALUES (:v)"), {"v": VERSION})
        return {"status": "applied", "version": VERSION, "legacy_owner": "chuso", "tables": tables}


def require_ready(engine):
    if engine.dialect.name != "postgresql":
        return
    with engine.connect() as conn:
        if "spend_schema_versions" not in inspect(conn).get_table_names():
            raise RuntimeError(
                "Apply the private-ledger database migration before deploying this version"
            )
        if not conn.execute(
            text("SELECT 1 FROM spend_schema_versions WHERE version=:v"), {"v": VERSION}
        ).scalar():
            raise RuntimeError("Private-ledger database migration is missing")
    # Verify the actual runtime identity and grants, not just the migration marker.
    from backend.tenancy import LedgerSession
    from backend.finance_models import Preference

    with LedgerSession(engine, user_id=OWNER_ID) as db:
        db.query(Preference).limit(1).all()
