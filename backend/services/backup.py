"""Full V2 ledger JSON export and idempotent cross-entity restore service."""

from datetime import date, datetime
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from backend import models
from backend.finance_models import (
    Budget,
    Category,
    Contribution,
    Goal,
    RecurringBill,
    Transaction,
)
from backend.schemas.finance import ImportLedgerInput
from backend.tenancy import OWNER_ID


def export_ledger_data(
    db: Session,
    *,
    preferences_fn: Callable[[Session], Dict[str, Any]],
    month_range_fn: Callable[[str], tuple[date, date]],
    year: Optional[int] = None,
    month: Optional[str] = None,
) -> Dict[str, Any]:
    cats = db.query(Category).order_by(Category.id).all()
    cat_map = {c.id: (c.name, c.color) for c in cats}
    tx_query = db.query(Transaction).filter(Transaction.deleted_at.is_(None))
    if month:
        start, end = month_range_fn(month)
        tx_query = tx_query.filter(Transaction.spent_on >= start, Transaction.spent_on < end)
    elif year is not None:
        tx_query = tx_query.filter(
            Transaction.spent_on >= date(year, 1, 1),
            Transaction.spent_on < date(year + 1, 1, 1),
        )
    rows = tx_query.order_by(Transaction.spent_on.desc(), Transaction.id.desc()).limit(10000).all()

    all_budgets = db.query(Budget).order_by(Budget.month.desc(), Budget.key).all()
    all_bills = db.query(RecurringBill).order_by(RecurringBill.id).all()
    all_goals = db.query(Goal).order_by(Goal.id).all()
    contribs_by_goal: Dict[int, list] = {}
    for c in db.query(Contribution).order_by(Contribution.saved_on.asc(), Contribution.id.asc()):
        contribs_by_goal.setdefault(c.goal_id, []).append(
            {
                "client_id": c.client_id,
                "amount": int(c.amount),
                "saved_on": c.saved_on.isoformat(),
            }
        )
    all_plans = (
        db.query(models.Plan)
        .order_by(models.Plan.created_at.desc(), models.Plan.id.desc())
        .limit(200)
        .all()
    )

    return {
        "version": 2,
        "exported_at": models.utc_now().isoformat(),
        "categories": [
            {"id": c.id, "name": c.name, "color": c.color, "archived": c.archived} for c in cats
        ],
        "transactions": [
            {
                "client_id": r.client_id,
                "title": r.title,
                "amount": r.amount,
                "kind": r.kind,
                "spent_on": r.spent_on.isoformat(),
                "category_id": r.category_id,
                "category_name": cat_map.get(r.category_id, ("Khác", "slate"))[0],
                "category_color": cat_map.get(r.category_id, ("Khác", "slate"))[1],
                "note": r.note,
            }
            for r in rows
        ],
        "budgets": [
            {
                "month": b.month.strftime("%Y-%m"),
                "amount": int(b.amount),
                "category_name": (
                    cat_map.get(b.category_id, (None, None))[0] if b.category_id else None
                ),
            }
            for b in all_budgets
        ],
        "recurring_bills": [
            {
                "name": b.name,
                "amount": int(b.amount),
                "category_name": cat_map.get(b.category_id, ("Khác", "slate"))[0],
                "next_due": b.next_due.isoformat(),
                "frequency": b.frequency,
                "archived": b.archived,
            }
            for b in all_bills
        ],
        "goals": [
            {
                "name": g.name,
                "target": int(g.target),
                "deadline": g.deadline.isoformat() if g.deadline else None,
                "archived": g.archived,
                "contributions": contribs_by_goal.get(g.id, []),
            }
            for g in all_goals
        ],
        "plans": [
            {
                "title": p.title,
                "plan_type": p.plan_type,
                "total_budget": int(p.total_budget),
                "estimated_cost": int(p.estimated_cost),
                "region": p.region,
                "advice": p.advice or "",
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "items": [
                    {
                        "category": i.category,
                        "time_or_day": i.time_or_day,
                        "name": i.name,
                        "details": i.details or "",
                        "price": int(i.price),
                        "is_completed": bool(i.is_completed),
                    }
                    for i in (p.items or [])
                ],
            }
            for p in all_plans
        ],
        "preferences": preferences_fn(db),
    }


def import_ledger_data(
    db: Session,
    payload: ImportLedgerInput,
    *,
    save_preferences_fn: Callable[..., Any],
    commit_fn: Callable[[Session], None],
) -> Dict[str, Any]:
    user_id = db.info.get("user_id", OWNER_ID)
    existing_cats = {c.name.lower(): c for c in db.query(Category).all()}
    existing_clients = {
        cid for (cid,) in db.query(Transaction.client_id).all() if isinstance(cid, str)
    }

    def ensure_cat(name: str, color: str = "indigo", archived: bool = False) -> Category:
        clean_name = (name or "").strip() or "Khác"
        cat = existing_cats.get(clean_name.lower())
        if cat is None:
            cat = Category(name=clean_name[:80], color=color, archived=archived)
            db.add(cat)
            db.flush()
            existing_cats[clean_name.lower()] = cat
        elif cat.archived and not archived:
            cat.archived = False
        return cat

    for cat_item in payload.categories:
        ensure_cat(cat_item.name, cat_item.color, cat_item.archived)

    imported = 0
    skipped = 0
    for item in payload.transactions:
        cid = (item.client_id or "").strip() or str(uuid4())
        if cid in existing_clients or cid.startswith("plan-completion:"):
            skipped += 1
            continue
        cat = ensure_cat(item.category_name, item.category_color, archived=False)
        db.add(
            Transaction(
                client_id=cid[:80],
                title=item.title,
                amount=item.amount,
                kind=item.kind,
                spent_on=item.spent_on,
                category_id=cat.id,
                note=item.note,
            )
        )
        existing_clients.add(cid)
        imported += 1

    restored_budgets = 0
    for b_item in payload.budgets:
        start_month = date.fromisoformat(b_item.month + "-01")
        cat_id = ensure_cat(b_item.category_name).id if b_item.category_name else None
        b_key = f"{b_item.month}:{cat_id or 'all'}"
        row = db.get(Budget, (user_id, b_key))
        if row is None:
            db.add(Budget(key=b_key, month=start_month, category_id=cat_id, amount=b_item.amount))
            restored_budgets += 1

    existing_bills = {(b.name.lower(), b.frequency) for b in db.query(RecurringBill).all()}
    restored_bills = 0
    for bill_item in payload.recurring_bills:
        sig = (bill_item.name.lower(), bill_item.frequency)
        if sig in existing_bills:
            continue
        cat = ensure_cat(bill_item.category_name)
        db.add(
            RecurringBill(
                name=bill_item.name,
                amount=bill_item.amount,
                category_id=cat.id,
                next_due=bill_item.next_due,
                frequency=bill_item.frequency,
                anchor_day=bill_item.next_due.day,
                archived=bill_item.archived,
            )
        )
        existing_bills.add(sig)
        restored_bills += 1

    existing_goals = {g.name.lower(): g for g in db.query(Goal).all()}
    existing_contrib_ids = {
        cid for (cid,) in db.query(Contribution.client_id).all() if isinstance(cid, str)
    }
    restored_goals = 0
    for g_item in payload.goals:
        goal_obj = existing_goals.get(g_item.name.lower())
        if goal_obj is None:
            goal_obj = Goal(
                name=g_item.name,
                target=g_item.target,
                deadline=g_item.deadline,
                archived=g_item.archived,
            )
            db.add(goal_obj)
            db.flush()
            existing_goals[g_item.name.lower()] = goal_obj
            restored_goals += 1
        for c_item in g_item.contributions:
            c_cid = (c_item.client_id or "").strip() or str(uuid4())
            if c_cid in existing_contrib_ids:
                continue
            db.add(
                Contribution(
                    goal_id=goal_obj.id,
                    client_id=c_cid[:80],
                    amount=c_item.amount,
                    saved_on=c_item.saved_on,
                )
            )
            existing_contrib_ids.add(c_cid)

    existing_plans = {
        (p.title.lower(), p.plan_type, p.total_budget) for p in db.query(models.Plan).all()
    }
    restored_plans = 0
    for p_item in payload.plans:
        sig = (p_item.title.lower(), p_item.plan_type, p_item.total_budget)
        if sig in existing_plans:
            continue
        plan_obj = models.Plan(
            title=p_item.title,
            plan_type=p_item.plan_type,
            total_budget=p_item.total_budget,
            estimated_cost=p_item.estimated_cost or sum(i.price for i in p_item.items),
            actual_spent=0,
            region=p_item.region or "Việt Nam",
            advice=p_item.advice or "",
        )
        if p_item.created_at:
            try:
                plan_obj.created_at = datetime.fromisoformat(p_item.created_at)
            except ValueError:
                pass
        plan_obj.items = [
            models.PlanItem(
                category=sub.category,
                time_or_day=sub.time_or_day,
                name=sub.name,
                details=sub.details,
                price=sub.price,
                is_completed=sub.is_completed,
            )
            for sub in p_item.items
        ]
        db.add(plan_obj)
        existing_plans.add(sig)
        restored_plans += 1

    if payload.preferences is not None:
        save_preferences_fn(payload.preferences, db=db)
    else:
        commit_fn(db)

    has_v2_entities = any(
        (
            payload.version >= 2,
            payload.budgets,
            payload.recurring_bills,
            payload.goals,
            payload.plans,
            payload.preferences is not None,
        )
    )
    if not has_v2_entities:
        return {"imported": imported, "skipped": skipped}
    return {
        "imported": imported,
        "skipped": skipped,
        "restored_budgets": restored_budgets,
        "restored_bills": restored_bills,
        "restored_goals": restored_goals,
        "restored_plans": restored_plans,
    }
