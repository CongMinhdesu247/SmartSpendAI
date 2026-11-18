"""Unit tests for security hardening, recurring bills, 2-way sync, V2 backup & AI coach."""

from datetime import date
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request as StarletteRequest

from backend import ai_service, api_server, database, finance_api, models
from backend.access import (
    AccessMiddleware,
    AccessSettings,
    LoginLimiter,
    _is_safe_local_host,
    extract_client_ip,
    install_access,
    password_hasher,
)
from backend.auth_models import Account
from backend.routers import plans as plans_router, system as system_router
from backend.routers.auth import build_auth_router
from backend.schemas.access import LoginInput
from backend.schemas.finance import (
    AIReviewInput,
    BillInput,
    BillPayment,
    BudgetInput,
    ContributionInput,
    GoalInput,
    ImportLedgerInput,
    ImportTransactionItem,
    PreferencesInput,
    TransactionInput,
)
from backend.schemas.plans import (
    CreatePlanItemRequest,
    CreatePlanRequest,
    PatchItemRequest,
    UpdatePlanRequest,
)
from backend.tenancy import OWNER_ID, LedgerSession


class SecurityAndBusinessLogicTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        database.Base.metadata.create_all(self.engine)
        finance_api.initialize_finance(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_cloud_registration_is_locked_by_default_and_supports_invite_code(self):
        hashed = password_hasher.hash("Test-Owner-Password-123")
        base_env = {
            "SMARTSPEND_CLOUD": "1",
            "SMARTSPEND_PASSWORD_HASH": hashed,
            "SMARTSPEND_SESSION_SECRET": "s" * 40,
            "SMARTSPEND_PUBLIC_URL": "https://smartspend.example.com",
        }
        with patch.dict(os.environ, base_env, clear=True):
            settings = AccessSettings.from_environment()
            self.assertTrue(settings.accounts)
            self.assertFalse(settings.can_register)

        with patch.dict(
            os.environ, {**base_env, "SMARTSPEND_INVITE_CODE": "family-2026"}, clear=True
        ):
            invited = AccessSettings.from_environment()
            self.assertTrue(invited.can_register)
            self.assertEqual(invited.invite_code, "family-2026")

    def test_login_limiter_prevents_global_dos_across_different_ips(self):
        limiter = LoginLimiter()
        # 40 distinct attacker IPs must NOT lock out the legitimate owner IP
        for idx in range(40):
            self.assertTrue(limiter.allow(f"203.0.113.{idx}", "random_bot"))
        self.assertTrue(limiter.allow("198.51.100.77", "chuso"))
        # Same IP brute-forcing the same account is still capped at 8 attempts
        for _ in range(7):
            self.assertTrue(limiter.allow("198.51.100.77", "chuso"))
        self.assertFalse(limiter.allow("198.51.100.77", "chuso"))

    def test_dns_rebinding_host_guard(self):
        self.assertTrue(_is_safe_local_host("localhost:8000"))
        self.assertTrue(_is_safe_local_host("127.0.0.1:8000"))
        self.assertTrue(_is_safe_local_host("192.168.1.25:8000"))
        self.assertFalse(_is_safe_local_host("evil-rebind.attacker.com:8000"))

    def test_recurring_bill_delete_rolls_back_due_date_and_allows_repayment(self):
        with LedgerSession(self.engine, user_id=OWNER_ID) as db:
            cat_id = finance_api.categories(db=db)[0]["id"]
            bill = finance_api.create_bill(
                BillInput(
                    name="Internet",
                    amount=220000,
                    category_id=cat_id,
                    next_due=date(2026, 11, 15),
                    frequency="monthly",
                ),
                db=db,
            )
            tx = finance_api.pay_bill(
                bill["id"],
                BillPayment(due_on=date(2026, 11, 15), spent_on=date(2026, 11, 15)),
                db=db,
            )
            req = SimpleNamespace(headers={})
            self.assertEqual(finance_api.bills(req, db=db)[0]["next_due"], "2026-12-15")

            # Deleting the mistaken payment rolls next_due back to 2026-11-15
            finance_api.delete_transaction(tx["id"], db=db)
            self.assertEqual(finance_api.bills(req, db=db)[0]["next_due"], "2026-11-15")

            # Paying again for 2026-11-15 succeeds instead of deadlocking with 409
            repaid = finance_api.pay_bill(
                bill["id"],
                BillPayment(due_on=date(2026, 11, 15), spent_on=date(2026, 11, 16)),
                db=db,
            )
            self.assertEqual(repaid["id"], tx["id"])
            self.assertFalse(repaid["deleted"])
            self.assertEqual(finance_api.bills(req, db=db)[0]["next_due"], "2026-12-15")

    def test_manual_plan_crud_two_way_sync_archive_and_import_deduplication(self):
        with LedgerSession(self.engine, user_id=OWNER_ID) as db:
            cat_id = finance_api.categories(db=db)[0]["id"]
            plan = plans_router.create_manual_plan(
                CreatePlanRequest(
                    title="Đi chợ cuối tuần",
                    plan_type="meal",
                    total_budget=400000,
                    region="Hà Nội",
                ),
                db=db,
            )
            added = plans_router.add_plan_item(
                plan["id"],
                CreatePlanItemRequest(
                    category="grocery",
                    time_or_day="Đạm",
                    name="Thịt bò",
                    price=120000,
                ),
                db=db,
            )
            item_id = added["item"]["id"]
            self.assertEqual(added["plan"]["estimated_cost"], 120000)

            # Manual transaction creation marks PlanItem completed
            tx = finance_api.create_transaction(
                TransactionInput(
                    client_id=uuid4(),
                    title="Thịt bò",
                    amount=115000,
                    kind="expense",
                    spent_on=date(2026, 11, 18),
                    category_id=cat_id,
                    source_item_id=item_id,
                ),
                db=db,
            )
            self.assertTrue(
                plans_router.get_plan_detail(plan["id"], db=db)["items"][0]["is_completed"]
            )

            # Deleting transaction unchecks PlanItem; restoring re-checks it
            finance_api.delete_transaction(tx["id"], db=db)
            self.assertFalse(
                plans_router.get_plan_detail(plan["id"], db=db)["items"][0]["is_completed"]
            )
            self.assertEqual(len(finance_api.list_archive(db=db)["transactions"]), 1)

            finance_api.restore_transaction(tx["id"], db=db)
            self.assertTrue(
                plans_router.get_plan_detail(plan["id"], db=db)["items"][0]["is_completed"]
            )

            # Edit plan & item, then delete item
            edited_plan = plans_router.update_plan(
                plan["id"], UpdatePlanRequest(title="Đi chợ mới", total_budget=600000), db=db
            )
            self.assertEqual(edited_plan["title"], "Đi chợ mới")
            plans_router.update_plan_item(
                item_id, PatchItemRequest(name="Thịt bò Mỹ", time_or_day="Sáng"), db=db
            )
            after_del = plans_router.delete_plan_item(item_id, db=db)
            self.assertEqual(after_del["plan"]["estimated_cost"], 0)

            # Export & idempotent re-import
            exported = finance_api.export_ledger(year=2026, month=None, db=db)
            self.assertEqual(len(exported["transactions"]), 1)
            reimport = finance_api.import_ledger(
                ImportLedgerInput(
                    transactions=[
                        ImportTransactionItem(**exported["transactions"][0]),
                        ImportTransactionItem(
                            title="Khoản mới",
                            amount=50000,
                            kind="expense",
                            spent_on=date(2026, 11, 18),
                            category_name="Danh mục mới",
                        ),
                    ]
                ),
                db=db,
            )
            self.assertEqual(reimport, {"imported": 1, "skipped": 1})

    def test_proxy_ip_extraction_and_login_refund_prevent_shared_tunnel_lockout(self):
        limiter = LoginLimiter()
        # Legitimate user logging in 25 times in a row with refund_success never locks out
        for _ in range(25):
            self.assertTrue(limiter.allow("203.0.113.10", "chuso"))
            limiter.refund_success("203.0.113.10", "chuso")

        # Untrusted or direct public socket ignores spoofed headers
        untrusted_req = SimpleNamespace(
            client=SimpleNamespace(host="198.51.100.20"),
            headers={"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "1.2.3.4"},
        )
        self.assertEqual(extract_client_ip(untrusted_req, trust_proxy=True), "198.51.100.20")

        # Trusted Docker bridge / loopback proxy resolves real visitor IP safely
        docker_proxy_req = SimpleNamespace(
            client=SimpleNamespace(host="172.18.0.1"),
            headers={"cf-connecting-ip": "203.0.113.88"},
        )
        self.assertEqual(extract_client_ip(docker_proxy_req, trust_proxy=False), "172.18.0.1")
        self.assertEqual(extract_client_ip(docker_proxy_req, trust_proxy=True), "203.0.113.88")

    def test_deactivated_chuso_cannot_bypass_via_env_password_hash(self):
        env_pwd = "Env-Owner-Password-12345"
        db_pwd = "Updated-Owner-Password-67890"
        env_hash = password_hasher.hash(env_pwd)
        db_hash = password_hasher.hash(db_pwd)

        with Session(self.engine) as db:
            db.add(Account(id=OWNER_ID, username="chuso", password_hash=db_hash, active=False))
            db.commit()

        settings = AccessSettings(
            True, env_hash, "s" * 48, "https://smartspend.example.com", accounts=True
        )
        test_app = FastAPI()
        install_access(test_app, settings)
        auth_router = build_auth_router(test_app, settings)
        login_endpoint = next(r.endpoint for r in auth_router.routes if r.path == "/api/auth/login")
        fake_req = SimpleNamespace(
            client=SimpleNamespace(host="198.51.100.5"),
            headers={},
            session={},
        )
        with patch.object(database, "engine", self.engine):
            for candidate in (env_pwd, db_pwd):
                with self.assertRaises(HTTPException) as ctx:
                    login_endpoint(LoginInput(username="chuso", password=candidate), fake_req)
                self.assertEqual(ctx.exception.status_code, 401)

    def test_security_headers_body_size_guard_allowed_hosts_and_blocked_static(self):
        def step_coro(coro):
            try:
                coro.send(None)
                raise AssertionError("Coroutine yielded unexpectedly")
            except StopIteration as done:
                return done.value

        async def sync_threadpool(func, *args, **kwargs):
            return func(*args, **kwargs)

        def make_request(method, path, headers_dict):
            raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers_dict.items()]
            scope = {
                "type": "http",
                "http_version": "1.1",
                "method": method,
                "scheme": "https",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": raw_headers,
                "client": ("127.0.0.1", 50000),
                "server": ("smartspend.example.com", 443),
                "session": {},
            }
            return StarletteRequest(scope)

        hashed = password_hasher.hash("Test-Owner-Password-12345")
        settings = AccessSettings(
            True,
            hashed,
            "s" * 48,
            "https://smartspend.example.com",
            accounts=True,
            allowed_hosts=("192.168.1.50:8092",),
        )
        mw = AccessMiddleware(FastAPI(), settings)

        async def ok_next(_req):
            return JSONResponse({"ok": True})

        with (
            patch.object(database, "engine", self.engine),
            patch("backend.access.run_in_threadpool", side_effect=sync_threadpool),
        ):
            res = step_coro(
                mw.dispatch(
                    make_request("GET", "/api/auth/status", {"host": "smartspend.example.com"}),
                    ok_next,
                )
            )
            self.assertEqual(res.status_code, 200)
            self.assertIn("max-age=63072000", res.headers["strict-transport-security"])
            self.assertEqual(res.headers["cross-origin-opener-policy"], "same-origin")
            self.assertEqual(res.headers["cross-origin-resource-policy"], "same-origin")
            self.assertIn("camera=()", res.headers["permissions-policy"])
            self.assertIn("object-src 'none'", res.headers["content-security-policy"])

            # Allowed LAN host succeeds, unknown host returns 400
            lan_res = step_coro(
                mw.dispatch(
                    make_request("GET", "/api/auth/status", {"host": "192.168.1.50:8092"}),
                    ok_next,
                )
            )
            self.assertEqual(lan_res.status_code, 200)
            bad_host = step_coro(
                mw.dispatch(
                    make_request("GET", "/api/auth/status", {"host": "evil.invalid"}),
                    ok_next,
                )
            )
            self.assertEqual(bad_host.status_code, 400)

            # Oversized request body rejected with 413 before JSON parsing
            huge_res = step_coro(
                mw.dispatch(
                    make_request(
                        "POST",
                        "/api/auth/login",
                        {
                            "host": "smartspend.example.com",
                            "origin": "https://smartspend.example.com",
                            "content-length": str(600 * 1024),
                        },
                    ),
                    ok_next,
                )
            )
            self.assertEqual(huge_res.status_code, 413)

        # Static guard blocks tailwind.input.css and dotfiles
        guarded = api_server._GuardedStaticFiles(directory=str(api_server.FRONTEND_DIR), html=True)
        for blocked_path in ("tailwind.input.css", ".env"):
            with self.assertRaises(StarletteHTTPException) as exc_ctx:
                step_coro(guarded.get_response(blocked_path, {"type": "http"}))
            self.assertEqual(exc_ctx.exception.status_code, 404)

    def test_health_score_sorting_day_filter_full_v2_backup_ai_coach_and_db_healthz(self):
        second_user = str(uuid4())
        finance_api.initialize_finance(self.engine, user_id=second_user)

        with LedgerSession(self.engine, user_id=OWNER_ID) as db:
            cat_id = finance_api.categories(db=db)[0]["id"]
            finance_api.set_budget("2026-11", BudgetInput(amount=5_000_000), db=db)
            finance_api.create_transaction(
                TransactionInput(
                    client_id=uuid4(),
                    title="Lương tháng 11",
                    amount=15_000_000,
                    kind="income",
                    spent_on=date(2026, 11, 5),
                    category_id=cat_id,
                ),
                db=db,
            )
            finance_api.create_transaction(
                TransactionInput(
                    client_id=uuid4(),
                    title="Đi siêu thị",
                    amount=450_000,
                    kind="expense",
                    spent_on=date(2026, 11, 10),
                    category_id=cat_id,
                ),
                db=db,
            )
            finance_api.create_transaction(
                TransactionInput(
                    client_id=uuid4(),
                    title="Ăn sáng",
                    amount=35_000,
                    kind="expense",
                    spent_on=date(2026, 11, 12),
                    category_id=cat_id,
                ),
                db=db,
            )
            finance_api.create_bill(
                BillInput(
                    name="Điện nước",
                    amount=600_000,
                    category_id=cat_id,
                    next_due=date(2026, 11, 19),
                    frequency="monthly",
                ),
                db=db,
            )
            goal = finance_api.create_goal(
                GoalInput(name="Quỹ dự phòng", target=20_000_000, deadline=date(2027, 6, 1)),
                db=db,
            )
            finance_api.contribute(
                goal["id"],
                ContributionInput(client_id=uuid4(), amount=2_000_000, saved_on=date(2026, 11, 12)),
                db=db,
            )
            plan = plans_router.create_manual_plan(
                CreatePlanRequest(
                    title="Thực đơn tiết kiệm", plan_type="meal", total_budget=500_000
                ),
                db=db,
            )
            plans_router.add_plan_item(
                plan["id"],
                CreatePlanItemRequest(category="grocery", name="Ức gà", price=85_000),
                db=db,
            )
            finance_api.save_preferences(
                PreferencesInput(people="3 người", tastes="Ít dầu mỡ", avoid="Nội tạng"), db=db
            )

            with patch("backend.finance_api.today", return_value=date(2026, 11, 18)):
                ov = finance_api.overview("2026-11", db=db)
            self.assertGreaterEqual(ov["health_score"]["score"], 80)
            self.assertEqual(ov["highlights"]["top_expense"]["amount"], 450_000)
            self.assertEqual(len(ov["highlights"]["due_soon_bills"]), 1)
            self.assertGreater(ov["insights"]["no_spend_days"], 0)

            # Day filter & amount sorting
            day_rows = finance_api.transactions(
                month="2026-11", day=date(2026, 11, 10), db=db
            )
            self.assertEqual(day_rows["total"], 1)
            self.assertEqual(day_rows["items"][0]["title"], "Đi siêu thị")

            sorted_rows = finance_api.transactions(
                month="2026-11", kind="expense", sort="amount_asc", db=db
            )
            self.assertEqual([r["amount"] for r in sorted_rows["items"]], [35_000, 450_000])

            # AI Coach review
            fake_coaching = {
                "headline": "Dòng tiền tháng 11 rất tích cực",
                "summary": "Bạn mới dùng 9% ngân sách tháng.",
                "strengths": ["Tỷ lệ tiết kiệm cao"],
                "warnings": [],
                "action_items": ["Duy trì mức chi dưới 350.000đ/ngày"],
                "suggested_daily_cap": 350_000,
            }
            with patch.object(ai_service, "analyze_monthly_spending", return_value=fake_coaching):
                coach_res = finance_api.ai_financial_review(
                    AIReviewInput(month="2026-11"), db=db
                )
            self.assertEqual(coach_res["coaching"]["suggested_daily_cap"], 350_000)

            # Full V2 Export
            full_backup = finance_api.export_ledger(year=None, month=None, db=db)
            self.assertEqual(full_backup["version"], 2)
            self.assertEqual(len(full_backup["goals"]), 1)
            self.assertEqual(len(full_backup["recurring_bills"]), 1)
            self.assertEqual(len(full_backup["plans"]), 1)

        # Restore V2 backup into an empty second user's ledger & verify idempotency
        with LedgerSession(self.engine, user_id=second_user) as db2:
            payload_v2 = ImportLedgerInput.model_validate(full_backup)
            res1 = finance_api.import_ledger(payload_v2, db=db2)
            self.assertEqual(res1["imported"], 3)
            self.assertEqual(res1["restored_goals"], 1)
            self.assertEqual(res1["restored_bills"], 1)
            self.assertEqual(res1["restored_plans"], 1)
            self.assertEqual(finance_api.goals(db=db2)[0]["saved"], 2_000_000)
            self.assertEqual(finance_api.preferences(db=db2)["people"], "3 người")
            self.assertEqual(len(plans_router.list_plans(db=db2)), 1)

            # Second import skips duplicates cleanly
            res2 = finance_api.import_ledger(payload_v2, db=db2)
            self.assertEqual(res2["imported"], 0)
            self.assertEqual(res2["skipped"], 3)
            self.assertEqual(res2["restored_plans"], 0)

        # DB-aware /healthz check
        with patch.object(database, "engine", self.engine), patch.object(
            database, "current_db_mode", "sqlite"
        ):
            self.assertEqual(system_router.health(), {"status": "ok", "db": "sqlite"})

    def test_chunked_body_guard_anti_spoof_ip_trends_and_budget_rollover(self):
        from backend.access import normalize_allowed_host

        def step_coro(coro):
            try:
                coro.send(None)
                raise AssertionError("Coroutine yielded unexpectedly")
            except StopIteration as done:
                return done.value

        async def sync_threadpool(func, *args, **kwargs):
            return func(*args, **kwargs)

        # 1. URL-formatted SMARTSPEND_ALLOWED_HOSTS normalizes cleanly
        self.assertEqual(normalize_allowed_host("https://192.168.1.50:8092/"), "192.168.1.50:8092")
        self.assertEqual(normalize_allowed_host("http://100.95.33.63:8092/app"), "100.95.33.63:8092")

        # 2. X-Real-IP from local Nginx/Caddy beats spoofed CF-Connecting-IP
        nginx_req = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"cf-connecting-ip": "1.2.3.4", "x-real-ip": "198.51.100.99"},
        )
        self.assertEqual(extract_client_ip(nginx_req, trust_proxy=True), "198.51.100.99")

        # 3. Chunked stream exceeding MAX_API_BODY_BYTES without Content-Length returns 413
        chunks = [
            {"type": "http.request", "body": b"x" * (200 * 1024), "more_body": True},
            {"type": "http.request", "body": b"y" * (100 * 1024), "more_body": False},
        ]

        async def fake_receive():
            return chunks.pop(0) if chunks else {"type": "http.request", "body": b""}

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/auth/login",
            "raw_path": b"/api/auth/login",
            "query_string": b"",
            "headers": [
                (b"host", b"smartspend.example.com"),
                (b"origin", b"https://smartspend.example.com"),
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("smartspend.example.com", 443),
            "session": {},
        }
        chunked_req = StarletteRequest(scope, receive=fake_receive)
        hashed = password_hasher.hash("Test-Owner-Password-12345")
        settings = AccessSettings(
            True, hashed, "s" * 48, "https://smartspend.example.com", accounts=True
        )
        mw = AccessMiddleware(FastAPI(), settings)

        async def consume_body_next(req):
            await req.body()
            return JSONResponse({"ok": True})

        with (
            patch.object(database, "engine", self.engine),
            patch("backend.access.run_in_threadpool", side_effect=sync_threadpool),
        ):
            res_413 = step_coro(mw.dispatch(chunked_req, consume_body_next))
            self.assertEqual(res_413.status_code, 413)

            # Root HTML sets Cache-Control: no-cache
            root_scope = {**scope, "method": "GET", "path": "/", "raw_path": b"/"}
            res_root = step_coro(
                mw.dispatch(StarletteRequest(root_scope), lambda _r: self._async_json({"ok": 1}))
            )
            self.assertEqual(res_root.headers["cache-control"], "no-cache")

        # 4. 6-Month Trends, End-of-Month Projection, 4-Pillar Score & Copy Previous Budgets
        with LedgerSession(self.engine, user_id=OWNER_ID) as db:
            cats = finance_api.categories(db=db)
            cat_active = cats[0]["id"]
            cat_to_archive = cats[1]["id"]
            finance_api.set_budget("2026-10", BudgetInput(amount=6_000_000), db=db)
            finance_api.set_budget(
                "2026-10", BudgetInput(amount=2_000_000, category_id=cat_active), db=db
            )
            finance_api.set_budget(
                "2026-10", BudgetInput(amount=500_000, category_id=cat_to_archive), db=db
            )
            finance_api.archive_category(cat_to_archive, db=db)

            finance_api.create_transaction(
                TransactionInput(
                    client_id=uuid4(),
                    title="Lương tháng 10",
                    amount=12_000_000,
                    kind="income",
                    spent_on=date(2026, 10, 5),
                    category_id=cat_active,
                ),
                db=db,
            )
            finance_api.create_transaction(
                TransactionInput(
                    client_id=uuid4(),
                    title="Chi tháng 11",
                    amount=1_800_000,
                    kind="expense",
                    spent_on=date(2026, 11, 15),
                    category_id=cat_active,
                ),
                db=db,
            )

            copied = finance_api.copy_previous_budgets("2026-11", db=db)
            self.assertEqual(copied["source_month"], "2026-10")
            self.assertEqual(copied["copied"], 2)  # Skips archived category!

            with patch("backend.finance_api.today", return_value=date(2026, 11, 15)):
                ov = finance_api.overview("2026-11", db=db)
                trends = finance_api.monthly_trends(months=6, end_month="2026-11", db=db)

            self.assertEqual(ov["budget"], 6_000_000)
            self.assertTrue(ov["has_previous_budgets"])
            self.assertEqual(len(ov["health_score"]["pillars"]), 4)
            self.assertEqual(ov["projection"]["projected_expense"], 3_600_000)
            self.assertEqual(len(trends["series"]), 6)
            self.assertEqual(trends["series"][-2]["income"], 12_000_000)
            self.assertEqual(trends["series"][-1]["expense"], 1_800_000)

    @staticmethod
    async def _async_json(payload):
        return JSONResponse(payload)


if __name__ == "__main__":
    unittest.main()
