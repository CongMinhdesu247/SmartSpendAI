"""Personal spending ledger, budgets, bills and savings. No AI needed for CRUD."""
import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID
from uuid import uuid5, NAMESPACE_URL

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import database, models
from backend.finance_models import Budget, Category, Contribution, Goal, Preference, RecurringBill, Transaction, normalize_search

router = APIRouter(prefix="/api/finance", tags=["Finance"])
MONEY_MAX = 9_000_000_000_000
DEFAULT_CATEGORIES = [("Ăn uống", "orange"), ("Đi chợ", "green"), ("Đi chơi", "violet"),
                      ("Di chuyển", "sky"), ("Nhà ở", "indigo"), ("Mua sắm", "pink"),
                      ("Sức khỏe", "teal"), ("Học tập", "blue"), ("Khác", "slate")]


def today():
    return datetime.now(timezone(timedelta(hours=7))).date()


def initialize_finance(engine):
    """Seed once without modifying any existing plans, prices or completion flags."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert
    with Session(engine) as db, db.begin():
        if db.get(Preference, "seeded"):
            return
        for name, color in DEFAULT_CATEGORIES:
            db.execute(insert(Category).values(name=name, color=color, archived=False).on_conflict_do_nothing(index_elements=["name"]))
        db.execute(insert(Preference).values(key="seeded", value="1").on_conflict_do_nothing(index_elements=["key"]))


class Named(BaseModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value):
        if not value.strip():
            raise ValueError("Tên không được để trống")
        return value.strip()


class CategoryInput(Named):
    name: str = Field(min_length=1, max_length=80)
    color: Literal["orange", "green", "violet", "sky", "indigo", "pink", "teal", "blue", "slate"] = "indigo"


class TransactionInput(BaseModel):
    client_id: UUID
    title: str = Field(min_length=1, max_length=255)
    amount: int = Field(gt=0, le=MONEY_MAX, strict=True)
    kind: Literal["expense", "income"] = "expense"
    spent_on: date
    category_id: int = Field(gt=0)
    note: str = Field(default="", max_length=2000)
    source_item_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("title")
    @classmethod
    def trim_title(cls, value):
        if not value.strip():
            raise ValueError("Nội dung không được để trống")
        return value.strip()


class BudgetInput(BaseModel):
    amount: int = Field(ge=0, le=MONEY_MAX, strict=True)
    category_id: Optional[int] = Field(default=None, gt=0)


class BillInput(Named):
    amount: int = Field(gt=0, le=MONEY_MAX, strict=True)
    category_id: int = Field(gt=0)
    next_due: date
    frequency: Literal["weekly", "monthly", "yearly"] = "monthly"


class BillPayment(BaseModel):
    due_on: date
    spent_on: date


class GoalInput(Named):
    target: int = Field(gt=0, le=MONEY_MAX, strict=True)
    deadline: Optional[date] = None


class ContributionInput(BaseModel):
    client_id: UUID
    amount: int = Field(gt=0, le=MONEY_MAX, strict=True)
    saved_on: date


class PreferencesInput(BaseModel):
    tastes: str = Field(default="", max_length=2000)
    avoid: str = Field(default="", max_length=2000)
    people: str = Field(default="2 người", max_length=80)


def found(db, model, key):
    obj = db.get(model, key)
    if obj is None:
        raise HTTPException(404, "Không tìm thấy dữ liệu")
    return obj


def valid_category(db, key, allow_archived=False):
    obj = found(db, Category, key)
    if obj.archived and not allow_archived:
        raise HTTPException(409, "Danh mục đã được lưu trữ. Hãy chọn danh mục khác.")
    return obj


def transaction_dict(row):
    return {"id": row.id, "client_id": row.client_id, "title": row.title, "amount": row.amount,
            "kind": row.kind, "spent_on": row.spent_on.isoformat(), "category_id": row.category_id,
            "note": row.note, "source_item_id": row.source_item_id, "recurring_id": row.recurring_id,
            "deleted": row.deleted_at is not None}


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Dữ liệu vừa thay đổi hoặc bị trùng. Hãy tải lại và thử lại.")


def month_range(value):
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


@router.get("/categories")
def categories(db: Session = Depends(database.get_db)):
    return [{"id": c.id, "name": c.name, "color": c.color, "archived": c.archived}
            for c in db.query(Category).order_by(Category.id).all()]


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
    duplicate = db.query(Category).filter(func.lower(Category.name) == payload.name.lower(), Category.id != category_id).first()
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


@router.get("/transactions")
def transactions(month: str, category_id: Optional[int] = None, q: str = Query("", max_length=255),
                 kind: Optional[Literal["expense", "income"]] = None,
                 offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                 db: Session = Depends(database.get_db)):
    start, end = month_range(month)
    query = db.query(Transaction).filter(Transaction.deleted_at.is_(None), Transaction.spent_on >= start, Transaction.spent_on < end)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if q.strip():
        query = query.filter(Transaction.search_title.contains(normalize_search(q.strip()), autoescape=True))
    if kind:
        query = query.filter(Transaction.kind == kind)
    total = query.count()
    rows = query.order_by(Transaction.spent_on.desc(), Transaction.id.desc()).offset(offset).limit(limit).all()
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
        found(db, models.PlanItem, payload.source_item_id)
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
            commit(db)
            return transaction_dict(previous)
    row = Transaction(**values)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # A retry from another tab/device may have won the unique key race.
        existing = db.query(Transaction).filter_by(client_id=values["client_id"]).first()
        if existing and all(getattr(existing, key) == value for key, value in values.items()):
            return transaction_dict(existing)
        raise HTTPException(409, "Giao dịch bị trùng. Hãy tải lại danh sách.")
    return transaction_dict(row)


@router.put("/transactions/{transaction_id}")
def edit_transaction(transaction_id: int, payload: TransactionInput, db: Session = Depends(database.get_db)):
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
    commit(db)
    return {"success": True}


@router.post("/transactions/{transaction_id}/restore")
def restore_transaction(transaction_id: int, db: Session = Depends(database.get_db)):
    row = found(db, Transaction, transaction_id)
    row.deleted_at = None
    commit(db)
    return transaction_dict(row)


@router.get("/overview")
def overview(month: str, db: Session = Depends(database.get_db)):
    start, end = month_range(month)
    totals = dict(db.query(Transaction.kind, func.sum(Transaction.amount)).filter(
        Transaction.deleted_at.is_(None), Transaction.spent_on >= start, Transaction.spent_on < end
    ).group_by(Transaction.kind).all())
    groups = db.query(Transaction.category_id, func.sum(Transaction.amount), func.count(Transaction.id)).filter(
        Transaction.deleted_at.is_(None), Transaction.kind == "expense", Transaction.spent_on >= start,
        Transaction.spent_on < end).group_by(Transaction.category_id).all()
    daily = db.query(Transaction.spent_on, func.sum(Transaction.amount)).filter(
        Transaction.deleted_at.is_(None), Transaction.kind == "expense", Transaction.spent_on >= start,
        Transaction.spent_on < end).group_by(Transaction.spent_on).order_by(Transaction.spent_on).all()
    budgets = db.query(Budget).filter(Budget.month == start).all()
    budget = next((b.amount for b in budgets if b.category_id is None), None)
    return {"income": int(totals.get("income", 0)), "expense": int(totals.get("expense", 0)),
            "budget": budget, "remaining": budget - int(totals.get("expense", 0)) if budget is not None else None,
            "categories": [{"category_id": key, "amount": int(amount), "count": count} for key, amount, count in groups],
            "daily": [{"date": d.isoformat(), "amount": int(amount)} for d, amount in daily],
            "budgets": [{"category_id": b.category_id, "amount": b.amount} for b in budgets]}


@router.put("/budgets/{month}")
def set_budget(month: str, payload: BudgetInput, db: Session = Depends(database.get_db)):
    start, _ = month_range(month)
    if payload.category_id:
        valid_category(db, payload.category_id)
    key = f"{month}:{payload.category_id or 'all'}"
    row = db.get(Budget, key)
    if row:
        row.amount = payload.amount
    else:
        db.add(Budget(key=key, month=start, **payload.model_dump()))
    commit(db)
    return {"success": True}


@router.get("/recurring")
def bills(db: Session = Depends(database.get_db)):
    return [{"id": b.id, "name": b.name, "amount": b.amount, "category_id": b.category_id,
             "next_due": b.next_due.isoformat(), "frequency": b.frequency,
             "overdue": b.next_due < today()} for b in db.query(RecurringBill).filter_by(archived=False).order_by(RecurringBill.next_due, RecurringBill.id)]


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


def next_due_date(bill):
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
    previous = db.query(Transaction).filter_by(recurring_id=bill_id, occurrence_on=payload.due_on).first()
    if previous:
        if previous.deleted_at:
            raise HTTPException(409, "Giao dịch kỳ này đã xóa. Khôi phục trong lịch sử thay vì thanh toán lại.")
        if row.next_due == payload.due_on:
            row.next_due = next_due_date(row)
            commit(db)
        return transaction_dict(previous)
    if row.next_due != payload.due_on:
        raise HTTPException(409, "Kỳ thanh toán đã thay đổi. Hãy tải lại.")
    transaction = Transaction(client_id=str(uuid5(NAMESPACE_URL, f"smartspend:bill:{row.id}:{payload.due_on}")), title=row.name,
                              amount=row.amount, kind="expense", spent_on=payload.spent_on,
                              category_id=row.category_id, recurring_id=row.id, occurrence_on=payload.due_on)
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


@router.get("/goals")
def goals(db: Session = Depends(database.get_db)):
    saved = dict(db.query(Contribution.goal_id, func.sum(Contribution.amount)).group_by(Contribution.goal_id).all())
    return [{"id": g.id, "name": g.name, "target": g.target, "saved": int(saved.get(g.id, 0)),
             "deadline": g.deadline.isoformat() if g.deadline else None}
            for g in db.query(Goal).filter_by(archived=False).order_by(Goal.id.desc())]


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


@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: int, db: Session = Depends(database.get_db)):
    row = found(db, Transaction, transaction_id)
    if row.deleted_at:
        raise HTTPException(404, "Giao dịch đã xóa")
    return transaction_dict(row)


@router.get("/goals/{goal_id}/contributions")
def contributions(goal_id: int, db: Session = Depends(database.get_db)):
    found(db, Goal, goal_id)
    return [{"id": c.id, "client_id": c.client_id, "amount": c.amount, "saved_on": c.saved_on.isoformat()}
            for c in db.query(Contribution).filter_by(goal_id=goal_id).order_by(Contribution.saved_on.desc(), Contribution.id.desc())]


@router.post("/goals/{goal_id}/contributions")
def contribute(goal_id: int, payload: ContributionInput, db: Session = Depends(database.get_db)):
    goal = found(db, Goal, goal_id)
    if goal.archived:
        raise HTTPException(409, "Mục tiêu đã được lưu trữ")
    existing = db.query(Contribution).filter_by(client_id=str(payload.client_id)).first()
    if existing:
        if existing.goal_id != goal_id or existing.amount != payload.amount or existing.saved_on != payload.saved_on:
            raise HTTPException(409, "Mã đóng góp đã được sử dụng")
        return {"id": existing.id}
    row = Contribution(goal_id=goal_id, client_id=str(payload.client_id), amount=payload.amount, saved_on=payload.saved_on)
    db.add(row)
    commit(db)
    return {"id": row.id}


@router.delete("/contributions/{contribution_id}")
def remove_contribution(contribution_id: int, db: Session = Depends(database.get_db)):
    db.delete(found(db, Contribution, contribution_id))
    commit(db)
    return {"success": True}


@router.get("/preferences")
def preferences(db: Session = Depends(database.get_db)):
    return {key: (db.get(Preference, key).value if db.get(Preference, key) else default)
            for key, default in (("tastes", ""), ("avoid", ""), ("people", "2 người"))}


@router.put("/preferences")
def save_preferences(payload: PreferencesInput, db: Session = Depends(database.get_db)):
    for key, value in payload.model_dump().items():
        row = db.get(Preference, key)
        if row:
            row.value = value
        else:
            db.add(Preference(key=key, value=value))
    commit(db)
    return payload.model_dump()
