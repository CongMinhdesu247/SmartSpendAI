"""Personal spending ledger, health score, multi-month trends, AI coach, archive & V2 backup router."""

import calendar
from datetime import date, timedelta
import json
import logging
from typing import Annotated, Any, Dict, Literal, Optional
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import database, models
from backend.ai_limits import ai_slot
from backend.finance_models import (
    Budget,
    Category,
    Contribution,
    Goal,
    PlanArchive,
    Preference,
    RecurringBill,
    Transaction,
    normalize_search,
)
from backend.schemas.finance import (
    AIReviewInput,
    BillInput,
    BillPayment,
    BudgetInput,
    CategoryInput,
    ContributionInput,
    EditTransactionInput,
    GoalInput,
    ImportLedgerInput,
    PreferencesInput,
    TransactionInput,
)
from backend.services.backup import export_ledger_data, import_ledger_data
from backend.services.insights import (
    compute_goal_pace,
    compute_health_score,
    compute_month_projection,
    compute_monthly_trends,
    compute_recurring_monthly_equivalent,
)
from backend.tenancy import OWNER_ID

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/finance", tags=["Finance"])


def _client_today(request: Optional[Request] = None) -> date:
    from backend import finance_api

    return finance_api.client_today(request)


def found(db: Session, model, key):
    obj = db.get(model, key)
    if obj is None:
        raise HTTPException(404, "Không tìm thấy dữ liệu")
    return obj


def valid_category(db: Session, key: int, allow_archived: bool = False):
    obj = found(db, Category, key)
    if obj.archived and not allow_archived:
        raise HTTPException(409, "Danh mục đã được lưu trữ. Hãy chọn danh mục khác.")
    return obj


def transaction_dict(row: Transaction) -> Dict[str, Any]:
    return {
        "id": row.id,
        "client_id": row.client_id,
        "title": row.title,
        "amount": row.amount,
        "kind": row.kind,
        "spent_on": row.spent_on.isoformat(),
        "category_id": row.category_id,
        "note": row.note,
        "source_item_id": row.source_item_id,
        "recurring_id": row.recurring_id,
        "deleted": row.deleted_at is not None,
    }


def commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Dữ liệu vừa thay đổi hoặc bị trùng. Hãy tải lại và thử lại.")


def month_range(value: str):
    try:
        start = date.fromisoformat(value + "-01")
    except ValueError:
        raise HTTPException(422, "Tháng phải có dạng YYYY-MM")
    if value != start.strftime("%Y-%m"):
        raise HTTPException(422, "Tháng không hợp lệ")
    try:
        end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    except ValueError:
        raise HTTPException(422, "Tháng nằm ngoài phạm vi hỗ trợ")
    return start, end


# =====================================================================
# DANH MỤC
# =====================================================================
@router.get("/categories")
def categories(db: Session = Depends(database.get_db)):
    return [
        {"id": c.id, "name": c.name, "color": c.color, "archived": c.archived}
        for c in db.query(Category).order_by(Category.id).all()
    ]


@router.post("/categories")
def create_category(payload: CategoryInput, db: Session = Depends(database.get_db)):
    row = db.query(Category).filter(func.lower(Category.name) == payload.name.lower()).first()
    if row:
        if not row.archived:
            raise HTTPException(409, "Danh mục đã tồn tại")
        row.archived = False
        row.color = payload.color
    else:
        row = Category(**payload.model_dump())
        db.add(row)
    commit(db)
    return {"id": row.id}


@router.put("/categories/{category_id}")
def edit_category(category_id: int, payload: CategoryInput, db: Session = Depends(database.get_db)):
    row = found(db, Category, category_id)
    duplicate = (
        db.query(Category)
        .filter(func.lower(Category.name) == payload.name.lower(), Category.id != category_id)
        .first()
    )
    if duplicate:
        raise HTTPException(409, "Tên danh mục đã tồn tại")
    row.name, row.color = payload.name, payload.color
    commit(db)
    return {"success": True}


@router.delete("/categories/{category_id}")
def archive_category(category_id: int, db: Session = Depends(database.get_db)):
    row = found(db, Category, category_id)
    if db.query(RecurringBill).filter_by(category_id=category_id, archived=False).first():
        raise HTTPException(409, "Hãy đổi danh mục của khoản định kỳ trước")
    row.archived = True
    commit(db)
    return {"success": True}


@router.post("/categories/{category_id}/restore")
def restore_category(category_id: int, db: Session = Depends(database.get_db)):
    row = found(db, Category, category_id)
    row.archived = False
    commit(db)
    return {"success": True}


# =====================================================================
# GIAO DỊCH THU / CHI
# =====================================================================
@router.get("/transactions")
def transactions(
    month: str,
    category_id: Optional[int] = None,
    q: Annotated[str, Query(max_length=255)] = "",
    kind: Optional[Literal["expense", "income"]] = None,
    day: Optional[date] = None,
    sort: Literal["date_desc", "date_asc", "amount_desc", "amount_asc"] = "date_desc",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(database.get_db),
):
    start, end = month_range(month)
    query = db.query(Transaction).filter(
        Transaction.deleted_at.is_(None), Transaction.spent_on >= start, Transaction.spent_on < end
    )
    if day is not None:
        query = query.filter(Transaction.spent_on == day)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if q.strip():
        query = query.filter(
            Transaction.search_title.contains(normalize_search(q.strip()), autoescape=True)
        )
    if kind:
        query = query.filter(Transaction.kind == kind)
    total = query.count()
    if sort == "amount_desc":
        ordering = (Transaction.amount.desc(), Transaction.spent_on.desc(), Transaction.id.desc())
    elif sort == "amount_asc":
        ordering = (Transaction.amount.asc(), Transaction.spent_on.desc(), Transaction.id.desc())
    elif sort == "date_asc":
        ordering = (Transaction.spent_on.asc(), Transaction.id.asc())
    else:
        ordering = (Transaction.spent_on.desc(), Transaction.id.desc())
    rows = query.order_by(*ordering).offset(offset).limit(limit).all()
    return {"items": [transaction_dict(r) for r in rows], "total": total}


@router.post("/transactions")
def create_transaction(payload: TransactionInput, db: Session = Depends(database.get_db)):
    values = payload.model_dump()
    values["client_id"] = str(payload.client_id)
    existing = db.query(Transaction).filter_by(client_id=values["client_id"]).first()
    if existing:
        if any(getattr(existing, key) != value for key, value in values.items()):
            raise HTTPException(409, "Mã giao dịch đã được dùng với nội dung khác")
        return transaction_dict(existing)
    valid_category(db, payload.category_id)
    if payload.source_item_id:
        plan_item = found(db, models.PlanItem, payload.source_item_id)
        if payload.kind != "expense":
            raise HTTPException(422, "Thanh toán kế hoạch phải là khoản chi")
        previous = db.query(Transaction).filter_by(source_item_id=payload.source_item_id).first()
        if previous:
            if previous.deleted_at is None:
                raise HTTPException(409, "Hạng mục đã được ghi chi. Hãy sửa giao dịch hiện có.")
            previous.deleted_at = None
            for key, value in values.items():
                if key != "client_id":
                    setattr(previous, key, value)
            plan_item.is_completed = True
            commit(db)
            return transaction_dict(previous)
        plan_item.is_completed = True
    row = Transaction(**values)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Transaction).filter_by(client_id=values["client_id"]).first()
        if existing and all(getattr(existing, key) == value for key, value in values.items()):
            return transaction_dict(existing)
        raise HTTPException(409, "Giao dịch bị trùng. Hãy tải lại danh sách.")
    return transaction_dict(row)


@router.put("/transactions/{transaction_id}")
def edit_transaction(
    transaction_id: int, payload: EditTransactionInput, db: Session = Depends(database.get_db)
):
    row = found(db, Transaction, transaction_id)
    if row.deleted_at:
        raise HTTPException(409, "Giao dịch đã bị xóa")
    if payload.source_item_id != row.source_item_id or str(payload.client_id) != row.client_id:
        raise HTTPException(409, "Không thể đổi liên kết của giao dịch")
    if (row.source_item_id or row.recurring_id) and payload.kind != "expense":
        raise HTTPException(422, "Giao dịch liên kết phải là khoản chi")
    valid_category(db, payload.category_id, allow_archived=payload.category_id == row.category_id)
    for key in ("title", "amount", "kind", "spent_on", "category_id", "note"):
        setattr(row, key, getattr(payload, key))
    commit(db)
    return transaction_dict(row)


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(database.get_db)):
    row = found(db, Transaction, transaction_id)
    row.deleted_at = models.utc_now()
    if row.source_item_id:
        linked_item = db.get(models.PlanItem, row.source_item_id)
        if linked_item is not None:
            linked_item.is_completed = False
    if row.recurring_id and row.occurrence_on:
        bill = db.get(RecurringBill, row.recurring_id)
        if bill is not None and bill.next_due > row.occurrence_on:
            newer_paid = (
                db.query(Transaction)
                .filter(
                    Transaction.recurring_id == bill.id,
                    Transaction.id != row.id,
                    Transaction.deleted_at.is_(None),
                    Transaction.occurrence_on > row.occurrence_on,
                )
                .first()
            )
            if not newer_paid:
                bill.next_due = row.occurrence_on
    commit(db)
    return {"success": True}


@router.post("/transactions/{transaction_id}/restore")
def restore_transaction(transaction_id: int, db: Session = Depends(database.get_db)):
    row = found(db, Transaction, transaction_id)
    row.deleted_at = None
    if row.source_item_id:
        linked_item = db.get(models.PlanItem, row.source_item_id)
        if linked_item is not None:
            linked_item.is_completed = True
    if row.recurring_id and row.occurrence_on:
        bill = db.get(RecurringBill, row.recurring_id)
        if bill is not None and bill.next_due == row.occurrence_on:
            bill.next_due = next_due_date(bill)
    commit(db)
    return transaction_dict(row)


@router.delete("/transactions/{transaction_id}/permanent")
def purge_transaction(transaction_id: int, db: Session = Depends(database.get_db)):
    row = found(db, Transaction, transaction_id)
    if row.deleted_at is None:
        raise HTTPException(409, "Chỉ xóa vĩnh viễn được giao dịch đã nằm trong thùng rác")
    db.delete(row)
    commit(db)
    return {"success": True}


@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: int, db: Session = Depends(database.get_db)):
    row = found(db, Transaction, transaction_id)
    if row.deleted_at:
        raise HTTPException(404, "Giao dịch đã xóa")
    return transaction_dict(row)


# =====================================================================
# BÁO CÁO THÁNG, XU HƯỚNG 6 THÁNG, ĐIỂM SỨC KHỎE & CỐ VẤN AI
# =====================================================================
@router.get("/overview")
def overview(month: str, request: Request = None, db: Session = Depends(database.get_db)):
    start, end = month_range(month)
    totals = dict(
        db.query(Transaction.kind, func.sum(Transaction.amount))
        .filter(
            Transaction.deleted_at.is_(None),
            Transaction.spent_on >= start,
            Transaction.spent_on < end,
        )
        .group_by(Transaction.kind)
        .all()
    )
    tx_count = (
        db.query(func.count(Transaction.id))
        .filter(
            Transaction.deleted_at.is_(None),
            Transaction.spent_on >= start,
            Transaction.spent_on < end,
        )
        .scalar()
        or 0
    )
    groups = (
        db.query(Transaction.category_id, func.sum(Transaction.amount), func.count(Transaction.id))
        .filter(
            Transaction.deleted_at.is_(None),
            Transaction.kind == "expense",
            Transaction.spent_on >= start,
            Transaction.spent_on < end,
        )
        .group_by(Transaction.category_id)
        .all()
    )
    daily = (
        db.query(
            Transaction.spent_on,
            func.sum(case((Transaction.kind == "expense", Transaction.amount), else_=0)),
            func.sum(case((Transaction.kind == "income", Transaction.amount), else_=0)),
        )
        .filter(
            Transaction.deleted_at.is_(None),
            Transaction.spent_on >= start,
            Transaction.spent_on < end,
        )
        .group_by(Transaction.spent_on)
        .order_by(Transaction.spent_on)
        .all()
    )
    budgets = db.query(Budget).filter(Budget.month == start).all()
    budget = next((b.amount for b in budgets if b.category_id is None), None)

    income_val = int(totals.get("income", 0))
    expense_val = int(totals.get("expense", 0))
    remaining_val = budget - expense_val if budget is not None else None

    prev_year = start.year - 1 if start.month == 1 else start.year
    prev_month_num = 12 if start.month == 1 else start.month - 1
    prev_start = date(prev_year, prev_month_num, 1)
    prev_totals = dict(
        db.query(Transaction.kind, func.sum(Transaction.amount))
        .filter(
            Transaction.deleted_at.is_(None),
            Transaction.spent_on >= prev_start,
            Transaction.spent_on < start,
        )
        .group_by(Transaction.kind)
        .all()
    )
    prev_expense = int(prev_totals.get("expense", 0))
    prev_income = int(prev_totals.get("income", 0))
    mom_expense_pct = (
        round(((expense_val - prev_expense) / prev_expense) * 100, 1) if prev_expense > 0 else None
    )

    now_date = _client_today(request)
    days_in_month = calendar.monthrange(start.year, start.month)[1]
    is_future_month = (now_date.year, now_date.month) < (start.year, start.month)
    if (now_date.year, now_date.month) == (start.year, start.month):
        elapsed_days = max(1, now_date.day)
        days_left = max(1, days_in_month - now_date.day + 1)
    elif now_date > start:
        elapsed_days = days_in_month
        days_left = 0
    else:
        elapsed_days = 1
        days_left = days_in_month

    daily_avg = round(expense_val / elapsed_days) if expense_val > 0 else 0
    safe_daily = (
        max(0, remaining_val // days_left)
        if (remaining_val is not None and days_left > 0)
        else None
    )
    savings_rate = (
        round(((income_val - expense_val) / income_val) * 100) if income_val > 0 else None
    )

    observed_days = 0 if is_future_month else elapsed_days
    spent_days_count = sum(
        1 for d, exp, _inc in daily if exp and exp > 0 and d.day <= observed_days
    )
    no_spend_days = max(0, observed_days - spent_days_count)

    biggest_row = (
        db.query(Transaction)
        .filter(
            Transaction.deleted_at.is_(None),
            Transaction.kind == "expense",
            Transaction.spent_on >= start,
            Transaction.spent_on < end,
        )
        .order_by(Transaction.amount.desc(), Transaction.id.desc())
        .first()
    )
    top_expense = (
        {
            "id": biggest_row.id,
            "title": biggest_row.title,
            "amount": int(biggest_row.amount),
            "spent_on": biggest_row.spent_on.isoformat(),
        }
        if biggest_row
        else None
    )

    top_category = None
    if groups and expense_val > 0:
        top_cat_id, top_cat_amt, _ = max(groups, key=lambda g: int(g[1]))
        cat_obj = db.get(Category, top_cat_id)
        top_category = {
            "category_id": top_cat_id,
            "name": cat_obj.name if cat_obj else "Danh mục",
            "color": cat_obj.color if cat_obj else "indigo",
            "amount": int(top_cat_amt),
            "share_pct": round((int(top_cat_amt) / expense_val) * 100),
        }

    upcoming_horizon = now_date + timedelta(days=5)
    active_bills = (
        db.query(RecurringBill)
        .filter(RecurringBill.archived.is_(False))
        .order_by(RecurringBill.next_due, RecurringBill.id)
        .all()
    )
    overdue_count = sum(1 for b in active_bills if b.next_due < now_date)
    due_soon_bills = [
        {
            "id": b.id,
            "name": b.name,
            "amount": int(b.amount),
            "next_due": b.next_due.isoformat(),
            "overdue": b.next_due < now_date,
            "days_until": (b.next_due - now_date).days,
        }
        for b in active_bills
        if b.next_due <= upcoming_horizon
    ]

    has_previous_budgets = (
        db.query(Budget.key).filter(Budget.month < start).limit(1).scalar() is not None
    )

    health_score = compute_health_score(
        income_val=income_val,
        expense_val=expense_val,
        budget=budget,
        elapsed_days=observed_days or 1,
        days_in_month=days_in_month,
        no_spend_days=no_spend_days,
        mom_expense_pct=mom_expense_pct,
        overdue_bills=overdue_count,
        tx_count=int(tx_count),
    )
    projection = compute_month_projection(
        expense_val=expense_val,
        budget=budget,
        observed_days=observed_days,
        days_in_month=days_in_month,
        days_left=days_left,
    )

    return {
        "income": income_val,
        "expense": expense_val,
        "budget": budget,
        "remaining": remaining_val,
        "categories": [
            {"category_id": key, "amount": int(amount), "count": count}
            for key, amount, count in groups
        ],
        "daily": [
            {"date": d.isoformat(), "amount": int(expense)}
            for d, expense, income in daily
            if expense
        ],
        "daily_cashflow": [
            {"date": d.isoformat(), "expense": int(expense), "income": int(income)}
            for d, expense, income in daily
        ],
        "budgets": [{"category_id": b.category_id, "amount": b.amount} for b in budgets],
        "has_previous_budgets": has_previous_budgets,
        "insights": {
            "previous_month": prev_start.strftime("%Y-%m"),
            "previous_expense": prev_expense,
            "previous_income": prev_income,
            "mom_expense_pct": mom_expense_pct,
            "net_savings": income_val - expense_val,
            "savings_rate": savings_rate,
            "daily_average_expense": daily_avg,
            "safe_daily_spend": safe_daily,
            "days_left": days_left,
            "transaction_count": int(tx_count),
            "no_spend_days": no_spend_days,
            "observed_days": observed_days,
            "monthly_recurring_commitment": compute_recurring_monthly_equivalent(active_bills),
        },
        "projection": projection,
        "health_score": health_score,
        "highlights": {
            "top_expense": top_expense,
            "top_category": top_category,
            "due_soon_bills": due_soon_bills,
            "overdue_bills_count": overdue_count,
        },
    }


@router.get("/trends")
def monthly_trends(
    months: Annotated[int, Query(ge=2, le=12)] = 6,
    end_month: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(database.get_db),
):
    if end_month:
        end_start, _ = month_range(end_month)
    else:
        today_val = _client_today(request)
        end_start = date(today_val.year, today_val.month, 1)
    return compute_monthly_trends(db, end_start, months=months)


@router.post("/ai-review")
def ai_financial_review(
    payload: AIReviewInput,
    request: Request = None,
    db: Session = Depends(database.get_db),
    _ai=Depends(ai_slot),
):
    from backend import ai_service

    report = overview(payload.month, request=request, db=db)
    cat_names = {c.id: c.name for c in db.query(Category).all()}
    summary_context = {
        "month": payload.month,
        "income_vnd": report["income"],
        "expense_vnd": report["expense"],
        "monthly_budget_vnd": report["budget"],
        "remaining_budget_vnd": report["remaining"],
        "projected_month_end_expense_vnd": report["projection"]["projected_expense"],
        "health_score": report["health_score"]["score"],
        "insights": report["insights"],
        "category_breakdown": [
            {
                "category": cat_names.get(item["category_id"], "Khác"),
                "amount_vnd": item["amount"],
                "tx_count": item["count"],
            }
            for item in sorted(report["categories"], key=lambda x: x["amount"], reverse=True)
        ],
        "top_expense": report["highlights"]["top_expense"],
        "due_soon_bills": report["highlights"]["due_soon_bills"],
        "user_focus": payload.focus.strip(),
    }
    db.rollback()  # Release transaction before network call
    try:
        coaching = ai_service.analyze_monthly_spending(summary_context)
        return {"month": payload.month, "coaching": coaching}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("AI financial review failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Chưa gọi được Cố vấn AI. Kiểm tra kết nối hoặc API key.")


@router.put("/budgets/{month}")
def set_budget(month: str, payload: BudgetInput, db: Session = Depends(database.get_db)):
    start, _ = month_range(month)
    if payload.category_id:
        valid_category(db, payload.category_id)
    key = f"{month}:{payload.category_id or 'all'}"
    row = db.get(Budget, (db.info.get("user_id", OWNER_ID), key))
    if row:
        row.amount = payload.amount
    else:
        db.add(Budget(key=key, month=start, **payload.model_dump()))
    commit(db)
    return {"success": True}


@router.post("/budgets/{month}/copy-previous")
def copy_previous_budgets(month: str, db: Session = Depends(database.get_db)):
    target_start, _ = month_range(month)
    latest_prev_month = (
        db.query(func.max(Budget.month)).filter(Budget.month < target_start).scalar()
    )
    if latest_prev_month is None:
        raise HTTPException(404, "Chưa tìm thấy hạn mức ngân sách ở các tháng trước để sao chép.")

    source_rows = db.query(Budget).filter(Budget.month == latest_prev_month).all()
    active_cat_ids = {
        cid for (cid,) in db.query(Category.id).filter(Category.archived.is_(False)).all()
    }
    user_id = db.info.get("user_id", OWNER_ID)
    copied = 0
    for src in source_rows:
        if src.category_id is not None and src.category_id not in active_cat_ids:
            continue
        b_key = f"{month}:{src.category_id or 'all'}"
        existing = db.get(Budget, (user_id, b_key))
        if existing:
            existing.amount = src.amount
        else:
            db.add(
                Budget(
                    key=b_key,
                    month=target_start,
                    category_id=src.category_id,
                    amount=src.amount,
                )
            )
        copied += 1

    commit(db)
    return {
        "success": True,
        "copied": copied,
        "source_month": latest_prev_month.strftime("%Y-%m"),
    }


# =====================================================================
# KHOẢN ĐỊNH KỲ
# =====================================================================
@router.get("/recurring")
def bills(request: Request = None, db: Session = Depends(database.get_db)):
    current_day = _client_today(request)
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": b.amount,
            "category_id": b.category_id,
            "next_due": b.next_due.isoformat(),
            "frequency": b.frequency,
            "overdue": b.next_due < current_day,
        }
        for b in db.query(RecurringBill)
        .filter_by(archived=False)
        .order_by(RecurringBill.next_due, RecurringBill.id)
    ]


@router.post("/recurring")
def create_bill(payload: BillInput, db: Session = Depends(database.get_db)):
    valid_category(db, payload.category_id)
    row = RecurringBill(**payload.model_dump(), anchor_day=payload.next_due.day)
    db.add(row)
    commit(db)
    return {"id": row.id}


@router.put("/recurring/{bill_id}")
def edit_bill(bill_id: int, payload: BillInput, db: Session = Depends(database.get_db)):
    row = found(db, RecurringBill, bill_id)
    valid_category(db, payload.category_id)
    if row.next_due != payload.next_due:
        row.anchor_day = payload.next_due.day
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    commit(db)
    return {"success": True}


def next_due_date(bill: RecurringBill) -> date:
    due = bill.next_due
    if bill.frequency == "weekly":
        return due + timedelta(days=7)
    year = due.year + (bill.frequency == "yearly" or due.month == 12)
    month = due.month if bill.frequency == "yearly" else due.month % 12 + 1
    return date(year, month, min(bill.anchor_day, calendar.monthrange(year, month)[1]))


@router.post("/recurring/{bill_id}/pay")
def pay_bill(bill_id: int, payload: BillPayment, db: Session = Depends(database.get_db)):
    row = db.query(RecurringBill).filter_by(id=bill_id, archived=False).with_for_update().first()
    if not row:
        raise HTTPException(404, "Không tìm thấy khoản định kỳ")
    previous = (
        db.query(Transaction).filter_by(recurring_id=bill_id, occurrence_on=payload.due_on).first()
    )
    if previous:
        if previous.deleted_at is not None:
            if row.next_due != payload.due_on:
                raise HTTPException(409, "Kỳ thanh toán đã thay đổi. Hãy tải lại.")
            previous.deleted_at = None
            previous.title = row.name
            previous.amount = row.amount
            previous.category_id = row.category_id
            previous.spent_on = payload.spent_on
            row.next_due = next_due_date(row)
            commit(db)
            return transaction_dict(previous)
        if row.next_due == payload.due_on:
            row.next_due = next_due_date(row)
            commit(db)
        return transaction_dict(previous)
    if row.next_due != payload.due_on:
        raise HTTPException(409, "Kỳ thanh toán đã thay đổi. Hãy tải lại.")
    transaction = Transaction(
        client_id=str(uuid5(NAMESPACE_URL, f"smartspend:bill:{row.id}:{payload.due_on}")),
        title=row.name,
        amount=row.amount,
        kind="expense",
        spent_on=payload.spent_on,
        category_id=row.category_id,
        recurring_id=row.id,
        occurrence_on=payload.due_on,
    )
    db.add(transaction)
    row.next_due = next_due_date(row)
    commit(db)
    return transaction_dict(transaction)


@router.delete("/recurring/{bill_id}")
def archive_bill(bill_id: int, db: Session = Depends(database.get_db)):
    found(db, RecurringBill, bill_id).archived = True
    commit(db)
    return {"success": True}


@router.post("/recurring/{bill_id}/restore")
def restore_bill(bill_id: int, db: Session = Depends(database.get_db)):
    row = found(db, RecurringBill, bill_id)
    valid_category(db, row.category_id)
    row.archived = False
    commit(db)
    return {"success": True}


# =====================================================================
# MỤC TIÊU TIẾT KIỆM
# =====================================================================
@router.get("/goals")
def goals(request: Request = None, db: Session = Depends(database.get_db)):
    current_day = _client_today(request)
    saved = dict(
        db.query(Contribution.goal_id, func.sum(Contribution.amount))
        .group_by(Contribution.goal_id)
        .all()
    )
    result = []
    for g in db.query(Goal).filter_by(archived=False).order_by(Goal.id.desc()):
        saved_amt = int(saved.get(g.id, 0))
        pace = compute_goal_pace(g, saved_amt, current_day)
        result.append(
            {
                "id": g.id,
                "name": g.name,
                "target": g.target,
                "saved": saved_amt,
                "deadline": g.deadline.isoformat() if g.deadline else None,
                **pace,
            }
        )
    return result


@router.post("/goals")
def create_goal(payload: GoalInput, db: Session = Depends(database.get_db)):
    row = Goal(**payload.model_dump())
    db.add(row)
    commit(db)
    return {"id": row.id}


@router.put("/goals/{goal_id}")
def edit_goal(goal_id: int, payload: GoalInput, db: Session = Depends(database.get_db)):
    row = found(db, Goal, goal_id)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    commit(db)
    return {"success": True}


@router.delete("/goals/{goal_id}")
def archive_goal(goal_id: int, db: Session = Depends(database.get_db)):
    found(db, Goal, goal_id).archived = True
    commit(db)
    return {"success": True}


@router.post("/goals/{goal_id}/restore")
def restore_goal(goal_id: int, db: Session = Depends(database.get_db)):
    found(db, Goal, goal_id).archived = False
    commit(db)
    return {"success": True}


@router.get("/goals/{goal_id}/contributions")
def contributions(goal_id: int, db: Session = Depends(database.get_db)):
    found(db, Goal, goal_id)
    return [
        {
            "id": c.id,
            "client_id": c.client_id,
            "amount": c.amount,
            "saved_on": c.saved_on.isoformat(),
        }
        for c in db.query(Contribution)
        .filter_by(goal_id=goal_id)
        .order_by(Contribution.saved_on.desc(), Contribution.id.desc())
    ]


@router.post("/goals/{goal_id}/contributions")
def contribute(goal_id: int, payload: ContributionInput, db: Session = Depends(database.get_db)):
    goal = found(db, Goal, goal_id)
    if goal.archived:
        raise HTTPException(409, "Mục tiêu đã được lưu trữ")
    existing = db.query(Contribution).filter_by(client_id=str(payload.client_id)).first()
    if existing:
        if (
            existing.goal_id != goal_id
            or existing.amount != payload.amount
            or existing.saved_on != payload.saved_on
        ):
            raise HTTPException(409, "Mã đóng góp đã được sử dụng")
        return {"id": existing.id}
    row = Contribution(
        goal_id=goal_id,
        client_id=str(payload.client_id),
        amount=payload.amount,
        saved_on=payload.saved_on,
    )
    db.add(row)
    commit(db)
    return {"id": row.id}


@router.delete("/contributions/{contribution_id}")
def remove_contribution(contribution_id: int, db: Session = Depends(database.get_db)):
    db.delete(found(db, Contribution, contribution_id))
    commit(db)
    return {"success": True}


# =====================================================================
# SỞ THÍCH NGƯỜNG DÙNG
# =====================================================================
@router.get("/preferences")
def preferences(db: Session = Depends(database.get_db)):
    user_id = db.info.get("user_id", OWNER_ID)
    result = {}
    for key, default in (("tastes", ""), ("avoid", ""), ("people", "2 người")):
        row = db.get(Preference, (user_id, key))
        result[key] = row.value if row else default
    return result


@router.put("/preferences")
def save_preferences(payload: PreferencesInput, db: Session = Depends(database.get_db)):
    user_id = db.info.get("user_id", OWNER_ID)
    for key, value in payload.model_dump().items():
        row = db.get(Preference, (user_id, key))
        if row:
            row.value = value
        else:
            db.add(Preference(key=key, value=value))
    commit(db)
    return payload.model_dump()


# =====================================================================
# KHO LƯU TRỮ & THÙNG RÁC + SAO LƯU / KHÔI PHỤC ĐẦY ĐỦ (V2)
# =====================================================================
@router.get("/archive")
def list_archive(db: Session = Depends(database.get_db)):
    deleted_tx = (
        db.query(Transaction)
        .filter(Transaction.deleted_at.is_not(None))
        .order_by(Transaction.deleted_at.desc(), Transaction.id.desc())
        .limit(50)
        .all()
    )
    archived_cats = (
        db.query(Category).filter_by(archived=True).order_by(Category.name.asc()).all()
    )
    archived_bills = (
        db.query(RecurringBill)
        .filter_by(archived=True)
        .order_by(RecurringBill.id.desc())
        .limit(50)
        .all()
    )
    archived_goals = (
        db.query(Goal).filter_by(archived=True).order_by(Goal.id.desc()).limit(50).all()
    )
    deleted_plans_raw = (
        db.query(PlanArchive)
        .filter_by(restored=False)
        .order_by(PlanArchive.deleted_at.desc(), PlanArchive.id.desc())
        .limit(30)
        .all()
    )
    deleted_plans = []
    for entry in deleted_plans_raw:
        try:
            snap = json.loads(entry.snapshot)
            deleted_plans.append(
                {
                    "archive_id": entry.id,
                    "title": snap.get("title", "Kế hoạch đã xóa"),
                    "plan_type": snap.get("plan_type", "meal"),
                    "total_budget": snap.get("total_budget", 0),
                    "deleted_at": entry.deleted_at.isoformat() if entry.deleted_at else None,
                }
            )
        except Exception:
            continue

    return {
        "transactions": [transaction_dict(t) for t in deleted_tx],
        "categories": [{"id": c.id, "name": c.name, "color": c.color} for c in archived_cats],
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": b.amount,
                "frequency": b.frequency,
                "next_due": b.next_due.isoformat(),
            }
            for b in archived_bills
        ],
        "goals": [{"id": g.id, "name": g.name, "target": g.target} for g in archived_goals],
        "plans": deleted_plans,
    }


@router.get("/export")
def export_ledger(
    year: Annotated[Optional[int], Query(ge=1970, le=2200)] = None,
    month: Optional[str] = None,
    db: Session = Depends(database.get_db),
):
    return export_ledger_data(
        db,
        preferences_fn=preferences,
        month_range_fn=month_range,
        year=year,
        month=month,
    )


@router.post("/import")
def import_ledger(payload: ImportLedgerInput, db: Session = Depends(database.get_db)):
    return import_ledger_data(
        db,
        payload,
        save_preferences_fn=save_preferences,
        commit_fn=commit,
    )
