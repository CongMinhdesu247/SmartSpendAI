"""Shared finance seeding, timezone helpers, and facade for backend.routers.finance."""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from backend.finance_models import Category, Preference
from backend.routers.finance import (  # noqa: F401
    ai_financial_review,
    archive_bill,
    archive_category,
    archive_goal,
    bills,
    categories,
    commit,
    compute_health_score,
    contribute,
    contributions,
    copy_previous_budgets,
    create_bill,
    create_category,
    create_goal,
    create_transaction,
    delete_transaction,
    edit_bill,
    edit_category,
    edit_goal,
    edit_transaction,
    export_ledger,
    found,
    get_transaction,
    goals,
    import_ledger,
    list_archive,
    month_range,
    monthly_trends,
    next_due_date,
    overview,
    pay_bill,
    preferences,
    purge_transaction,
    remove_contribution,
    restore_bill,
    restore_category,
    restore_goal,
    restore_transaction,
    router,
    save_preferences,
    set_budget,
    transaction_dict,
    transactions,
    valid_category,
)
from backend.tenancy import OWNER_ID

DEFAULT_CATEGORIES = [
    ("Ăn uống", "orange"),
    ("Đi chợ", "green"),
    ("Đi chơi", "violet"),
    ("Di chuyển", "sky"),
    ("Nhà ở", "indigo"),
    ("Mua sắm", "pink"),
    ("Sức khỏe", "teal"),
    ("Học tập", "blue"),
    ("Khác", "slate"),
]


def today() -> date:
    return datetime.now(timezone(timedelta(hours=7))).date()


def client_today(request: Optional[Request] = None) -> date:
    if request is not None:
        headers = getattr(request, "headers", None) or {}
        raw_offset = headers.get("x-smartspend-tz-offset", "").strip()
        if raw_offset:
            try:
                offset_minutes = int(raw_offset)
                if -840 <= offset_minutes <= 840:
                    return datetime.now(timezone(timedelta(minutes=-offset_minutes))).date()
            except ValueError:
                pass
    return today()


def initialize_finance(engine, user_id=OWNER_ID):
    """Seed once without modifying any existing plans, prices or completion flags."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    with Session(engine) as db, db.begin():
        if db.get(Preference, (user_id, "seeded")):
            return
        for name, color in DEFAULT_CATEGORIES:
            db.execute(
                insert(Category)
                .values(user_id=user_id, name=name, color=color, archived=False)
                .on_conflict_do_nothing(index_elements=["user_id", "name"])
            )
        db.execute(
            insert(Preference)
            .values(user_id=user_id, key="seeded", value="1")
            .on_conflict_do_nothing(index_elements=["user_id", "key"])
        )
