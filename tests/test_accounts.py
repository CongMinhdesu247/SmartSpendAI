"""Two independent clients exercise the real API; only disposable databases."""

import os
import unittest
import sqlite3
import tempfile
from pathlib import Path
from contextlib import closing
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from backend import database, models, api_server
from backend.access import AccessSettings, install_access, password_hasher
from backend.finance_api import initialize_finance
from backend.finance_models import Account, Transaction, Category
from backend.tenancy import OWNER_ID, LedgerSession

ORIGIN = "https://private-ledgers.example"
PASSWORD = "Isolated-test-password-123"


class PrivateLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hashed = password_hasher.hash(PASSWORD)

    def make_engine(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        database.Base.metadata.create_all(engine)
        return engine

    def setUp(self):
        self.engine = self.make_engine()
        initialize_finance(self.engine)
        with Session(self.engine) as db:
            if not db.get(Account, OWNER_ID):
                db.add(Account(id=OWNER_ID, username="chuso", password_hash=self.hashed))
            db.commit()
        self.patches = [
            patch.object(database, "engine", self.engine),
            patch.object(database, "SessionLocal", sessionmaker(self.engine)),
            patch.dict(os.environ, {"SMARTSPEND_CLOUD": "1"}),
        ]
        for p in self.patches:
            p.start()
        app = FastAPI()
        install_access(
            app, AccessSettings(True, self.hashed, "test-secret-" * 8, ORIGIN, accounts=True)
        )
        # Use the same endpoints and get_db dependency as production, with fresh middleware.
        app.router.routes.extend(
            r for r in api_server.app.router.routes if not r.path.startswith("/api/auth/")
        )
        self.app = app
        self.clients = []
        self.a = self.register("alice")
        self.b = self.register("bob")

    def client(self):
        client = TestClient(self.app, base_url=ORIGIN)
        client.headers["Origin"] = ORIGIN
        self.clients.append(client)
        return client

    def register(self, username):
        c = self.client()
        r = c.post("/api/auth/register", json={"username": username, "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)
        c.headers["X-SmartSpend-User"] = c.get("/api/auth/status").json()["user"]["id"]
        return c

    def tearDown(self):
        for c in self.clients:
            c.close()
        for p in reversed(self.patches):
            p.stop()
        self.engine.dispose()

    def expense(self, client, **extra):
        category = client.get("/api/finance/categories").json()[0]["id"]
        return {
            "client_id": str(uuid4()),
            "title": "Bữa sáng riêng",
            "amount": 35000,
            "spent_on": "2026-11-08",
            "category_id": category,
            **extra,
        }

    def plan(self):
        with LedgerSession(self.engine, user_id=self.a.headers["X-SmartSpend-User"]) as db:
            plan = models.Plan(title="Riêng của Alice", plan_type="meal", total_budget=100000)
            plan.items = [models.PlanItem(name="Rau", price=10000)]
            db.add(plan)
            db.commit()
            return plan.id, plan.items[0].id

    def test_distinct_seed_legacy_owner_and_registration_validation(self):
        ca = self.a.get("/api/finance/categories").json()
        cb = self.b.get("/api/finance/categories").json()
        self.assertEqual(len(ca), 9)
        self.assertTrue(set(r["id"] for r in ca).isdisjoint(r["id"] for r in cb))
        owner = self.client()
        r = owner.post("/api/auth/login", json={"username": "CHUSO", "password": PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(owner.get("/api/auth/status").json()["user"]["id"], OWNER_ID)
        self.assertEqual(
            self.client()
            .post("/api/auth/register", json={"username": "ALICE", "password": PASSWORD})
            .status_code,
            409,
        )
        self.assertEqual(
            self.client()
            .post("/api/auth/register", json={"username": "bad name", "password": PASSWORD})
            .status_code,
            422,
        )
        self.assertEqual(
            self.client()
            .post("/api/auth/register", json={"username": "short", "password": "short"})
            .status_code,
            422,
        )

    def test_members_use_shared_server_ai_without_technical_settings(self):
        for client in (self.a, self.b):
            response = client.get("/api/config")
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["can_edit_config"])
            self.assertNotIn("gemini_api_key_masked", response.json())
            self.assertNotIn("configured_url_masked", response.json()["db_status"])
            self.assertEqual(
                client.post(
                    "/api/config", json={"gemini_api_key": "member-cannot-change-global-key"}
                ).status_code,
                403,
            )

    def test_checkbox_payment_is_private_and_updates_own_month(self):
        result = {
            "title": "AI",
            "plan_type": "meal",
            "total_budget": 500000,
            "estimated_cost": 30000,
            "region": "HCM",
            "advice": "",
            "items": [
                {
                    "category": "grocery",
                    "name": "Rau",
                    "time_or_day": "Đi chợ",
                    "details": "",
                    "price": 30000,
                }
            ],
        }
        with patch("backend.api_server.generate_smart_plan", return_value=result):
            response = self.a.post("/api/plans/generate", json={})
        self.assertEqual(response.status_code, 200, response.text)
        item_id = response.json()["items"][0]["id"]
        self.assertEqual(
            self.b.patch(f"/api/items/{item_id}", json={"is_completed": True}).status_code, 404
        )
        with patch("backend.finance_api.today", return_value=date(2026, 11, 9)):
            for _ in range(2):
                response = self.a.patch(f"/api/items/{item_id}", json={"is_completed": True})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["plan"]["actual_spent"], 30000)
        self.assertEqual(self.a.get("/api/finance/overview?month=2026-11").json()["expense"], 30000)
        self.assertEqual(self.b.get("/api/finance/overview?month=2026-11").json()["expense"], 0)
        self.assertEqual(self.a.get("/api/finance/transactions?month=2026-11").json()["total"], 1)

    def test_transactions_overviews_and_cross_person_links(self):
        payload = self.expense(self.a)
        created = self.a.post("/api/finance/transactions", json=payload)
        self.assertEqual(created.status_code, 200, created.text)
        ident = created.json()["id"]
        for method, path, body in [
            ("get", f"/transactions/{ident}", None),
            ("delete", f"/transactions/{ident}", None),
            ("put", f"/transactions/{ident}", payload),
            ("post", f"/transactions/{ident}/restore", {}),
        ]:
            r = getattr(self.b, method)(
                "/api/finance" + path, **({"json": body} if body is not None else {})
            )
            self.assertEqual(r.status_code, 404, r.text)
        self.assertEqual(self.b.get("/api/finance/transactions?month=2026-11").json()["total"], 0)
        self.assertEqual(self.b.get("/api/finance/overview?month=2026-11").json()["expense"], 0)
        self.assertEqual(
            self.b.get("/api/finance/overview?month=2026-11").json()["daily_cashflow"], []
        )
        self.assertEqual(self.b.post("/api/finance/transactions", json=payload).status_code, 404)
        own = self.expense(self.b, client_id=payload["client_id"])
        self.assertEqual(self.b.post("/api/finance/transactions", json=own).status_code, 200)

    def test_preferences_budgets_categories_bills_and_goals_are_private(self):
        self.assertEqual(
            self.a.put("/api/finance/preferences", json={"tastes": "Riêng Alice"}).status_code, 200
        )
        self.assertEqual(self.b.get("/api/finance/preferences").json()["tastes"], "")
        for c, amount in [(self.a, 100000), (self.b, 200000)]:
            self.assertEqual(
                c.put("/api/finance/budgets/2026-11", json={"amount": amount}).status_code, 200
            )
            self.assertEqual(c.get("/api/finance/overview?month=2026-11").json()["budget"], amount)
        category = self.a.get("/api/finance/categories").json()[0]["id"]
        self.assertEqual(self.b.delete(f"/api/finance/categories/{category}").status_code, 404)
        bill = self.a.post(
            "/api/finance/recurring",
            json={
                "name": "Điện",
                "amount": 100000,
                "category_id": category,
                "next_due": "2026-11-08",
            },
        ).json()["id"]
        self.assertEqual(
            self.b.post(
                f"/api/finance/recurring/{bill}/pay",
                json={"due_on": "2026-11-08", "spent_on": "2026-11-08"},
            ).status_code,
            404,
        )
        goal = self.a.post("/api/finance/goals", json={"name": "Riêng", "target": 1000000}).json()[
            "id"
        ]
        self.assertEqual(
            self.b.post(
                f"/api/finance/goals/{goal}/contributions",
                json={"client_id": str(uuid4()), "amount": 10000, "saved_on": "2026-11-08"},
            ).status_code,
            404,
        )
        self.assertEqual(self.b.get("/api/finance/goals").json(), [])

    def test_plan_relationships_copy_trash_restore_and_items_are_private(self):
        plan, item = self.plan()
        self.assertEqual(self.b.get("/api/plans").json(), [])
        self.assertEqual(self.b.get(f"/api/plans/{plan}").status_code, 404)
        self.assertEqual(self.b.post(f"/api/plans/{plan}/copy").status_code, 404)
        self.assertEqual(self.b.patch(f"/api/items/{item}", json={"price": 1}).status_code, 404)
        self.assertEqual(
            self.b.post(
                "/api/finance/transactions", json=self.expense(self.b, source_item_id=item)
            ).status_code,
            404,
        )
        copied = self.a.post(f"/api/plans/{plan}/copy")
        self.assertEqual(copied.status_code, 200, copied.text)
        trashed = self.a.delete(f"/api/plans/{plan}").json()["undo_id"]
        self.assertEqual(self.b.post(f"/api/plans/trash/{trashed}/restore").status_code, 404)
        r = self.a.post(f"/api/plans/trash/{trashed}/restore")
        self.assertEqual(r.status_code, 200, r.text)

    def test_account_switch_guard_and_logout_all_only_own_sessions(self):
        r = self.a.get(
            "/api/finance/categories",
            headers={"X-SmartSpend-User": self.b.headers["X-SmartSpend-User"]},
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["code"], "ACCOUNT_CHANGED")
        self.assertEqual(self.a.post("/api/auth/logout-all").status_code, 200)
        self.assertEqual(self.a.get("/api/finance/categories").status_code, 401)
        self.assertEqual(self.b.get("/api/finance/categories").status_code, 200)
        self.assertEqual(
            self.b.post(
                "/api/auth/register",
                json={"username": "mallory", "password": PASSWORD},
                headers={"Origin": "https://evil.example"},
            ).status_code,
            403,
        )

    def test_orm_bulk_writes_and_owner_override_are_blocked(self):
        plan, _ = self.plan()
        with LedgerSession(self.engine, user_id=self.b.headers["X-SmartSpend-User"]) as db:
            self.assertEqual(db.query(models.Plan).filter_by(id=plan).update({"title": "No"}), 0)
            self.assertEqual(db.query(models.Plan).filter_by(id=plan).delete(), 0)
            db.add(Category(user_id=self.a.headers["X-SmartSpend-User"], name="Forged"))
            with self.assertRaises(Exception):
                db.flush()

    def test_populated_old_sqlite_has_backup_and_preserves_links(self):
        from backend.sqlite_upgrade import upgrade_local

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ledger.db"
            with closing(sqlite3.connect(path)) as conn, conn:
                conn.executescript(
                    Path(__file__)
                    .with_name("fixtures")
                    .joinpath("single_owner_sqlite.sql")
                    .read_text(encoding="utf-8")
                )
                conn.execute(
                    "INSERT INTO plans(id,title,plan_type,total_budget,estimated_cost,actual_spent,region,created_at) VALUES (7,'Old','meal',100000,10000,0,'VN',CURRENT_TIMESTAMP)"
                )
                conn.execute(
                    "INSERT INTO plan_items(id,plan_id,name,category,time_or_day,details,price,is_completed) VALUES (8,7,'Old item','grocery','','',10000,1)"
                )
                conn.execute(
                    "INSERT INTO spend_categories(id,name,color,archived) VALUES (9,'Original','blue',0)"
                )
                conn.execute(
                    "INSERT INTO spend_preferences(key,value) VALUES ('tastes','Old preference')"
                )
            engine = create_engine("sqlite:///" + path.as_posix())
            try:
                upgrade_local(engine)
                upgrade_local(engine)
                self.assertTrue(path.with_name("ledger.before_private_ledgers.db").exists())
                with LedgerSession(engine, user_id=OWNER_ID) as db:
                    plan = db.get(models.Plan, 7)
                    self.assertEqual(plan.items[0].id, 8)
                    self.assertTrue(plan.items[0].is_completed)
                    from backend.finance_models import Preference

                    self.assertEqual(db.get(Preference, "tastes").value, "Old preference")
                with LedgerSession(engine, user_id=str(uuid4())) as db:
                    self.assertEqual(db.query(models.Plan).count(), 0)
                    db.add(Category(name="Original"))
                    db.commit()
            finally:
                engine.dispose()


@unittest.skipUnless(
    os.environ.get("SMARTSPEND_TEST_POSTGRES_URL"), "Optional disposable PostgreSQL fixture"
)
class PostgresPrivateLedgerTests(PrivateLedgerTests):
    def test_runtime_connection_checks_schema_and_ledger_role(self):
        from backend.account_migration import require_ready

        require_ready(self.engine)

    def make_engine(self):
        from sqlalchemy.engine import make_url
        from backend.account_migration import upgrade

        url = os.environ["SMARTSPEND_TEST_POSTGRES_URL"]
        parsed = make_url(url)
        if parsed.host != "127.0.0.1" or parsed.database != "smartspend_accounts_test":
            raise RuntimeError(
                "Refusing to reset anything other than the named loopback test database"
            )
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            for role in ("anon", "authenticated"):
                conn.execute(
                    text(
                        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN CREATE ROLE {role} NOLOGIN; END IF; END $$"
                    )
                )
        upgrade(engine, self.hashed)
        return engine

    def test_rls_blocks_raw_sql_other_people_and_cross_person_foreign_keys(self):
        from sqlalchemy.exc import DBAPIError

        a_id = self.a.headers["X-SmartSpend-User"]
        b_id = self.b.headers["X-SmartSpend-User"]
        a_category = self.a.get("/api/finance/categories").json()[0]["id"]
        with LedgerSession(self.engine, user_id=b_id) as db:
            self.assertEqual(
                db.execute(
                    text("SELECT count(*) FROM spend_categories WHERE user_id=:u"), {"u": a_id}
                ).scalar(),
                0,
            )
            self.assertEqual(
                db.execute(
                    text("UPDATE spend_categories SET name='no' WHERE id=:i"), {"i": a_category}
                ).rowcount,
                0,
            )
            self.assertFalse(
                db.execute(
                    text("SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user")
                ).scalar()
            )
            with self.assertRaises(DBAPIError):
                db.execute(
                    text(
                        "INSERT INTO spend_categories(user_id,name,color,archived) VALUES (:u,'no','blue',false)"
                    ),
                    {"u": a_id},
                )
            db.rollback()
            with self.assertRaises(DBAPIError):
                db.execute(
                    text(
                        "INSERT INTO spend_transactions(user_id,client_id,title,search_title,amount,kind,spent_on,category_id,note,created_at) VALUES (:u,:client,'no','no',100,'expense',CURRENT_DATE,:cat,'',CURRENT_TIMESTAMP)"
                    ),
                    {"u": b_id, "client": str(uuid4()), "cat": a_category},
                )
                db.commit()
            db.rollback()
            with self.assertRaises(DBAPIError):
                db.execute(text("SELECT * FROM spend_accounts"))

    def test_populated_deployed_schema_migrates_without_changing_legacy_data(self):
        from pathlib import Path
        from backend.account_migration import upgrade

        with self.engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.exec_driver_sql(
                Path(__file__)
                .with_name("fixtures")
                .joinpath("single_owner_schema.sql")
                .read_text(encoding="utf-8")
            )
            conn.execute(
                text(
                    "INSERT INTO plans(id,title,plan_type,total_budget,estimated_cost,actual_spent,region,created_at) VALUES (77,'Sổ cũ','meal',500000,80000,80000,'Hà Nội',CURRENT_TIMESTAMP)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO plan_items(id,plan_id,name,category,time_or_day,details,price,is_completed) VALUES (88,77,'Cá','grocery','','',80000,true)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO spend_categories(id,name,color,archived) VALUES (99,'Cũ','blue',false)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO spend_transactions(id,client_id,title,search_title,amount,kind,spent_on,category_id,note,source_item_id,created_at) VALUES (101,'old-client','Cá','ca',80000,'expense','2026-11-08',99,'Giữ nguyên',88,CURRENT_TIMESTAMP)"
                )
            )
            conn.execute(
                text("INSERT INTO spend_preferences(key,value) VALUES ('tastes','Giữ nguyên')")
            )
            conn.execute(
                text(
                    "INSERT INTO spend_budgets(key,month,amount) VALUES ('2026-11:all','2026-11-01',500000)"
                )
            )
        result = upgrade(self.engine, self.hashed)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(upgrade(self.engine, self.hashed)["status"], "already_applied")
        with LedgerSession(self.engine, user_id=OWNER_ID) as db:
            plan = db.get(models.Plan, 77)
            self.assertEqual(
                (
                    plan.title,
                    plan.actual_spent,
                    plan.items[0].is_completed,
                    plan.items[0].paid_amount,
                ),
                ("Sổ cũ", 80000, True, 80000),
            )
            tx = db.get(Transaction, 101)
            self.assertEqual((tx.source_item_id, tx.note, tx.amount), (88, "Giữ nguyên", 80000))
            from backend.finance_models import Preference, Budget

            self.assertEqual(db.get(Preference, "tastes").value, "Giữ nguyên")
            self.assertEqual(db.get(Budget, "2026-11:all").amount, 500000)
        with LedgerSession(self.engine, user_id=str(uuid4())) as db:
            self.assertEqual(db.query(models.Plan).count(), 0)
            self.assertEqual(db.query(Transaction).count(), 0)


if __name__ == "__main__":
    unittest.main()
