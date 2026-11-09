"""Keep checkbox-created expenses idempotent without changing manual payments."""

from uuid import uuid4

from fastapi import HTTPException

from backend.finance_models import Category, Transaction
from backend.models import utc_now


AUTO_PREFIX = "plan-completion:"


def sync_completion_payment(db, item, payload):
    from backend.finance_api import today

    payment = db.query(Transaction).filter_by(source_item_id=item.id).first()
    automatic = payment is not None and payment.client_id.startswith(AUTO_PREFIX)
    if payload.is_completed is False:
        if automatic and payment.deleted_at is None:
            payment.deleted_at = utc_now()
        return
    # Price edits only follow an existing automatic payment. Old checkmarks are
    # never imported into the ledger merely by opening or renaming a plan.
    requested = payload.is_completed is True or (
        payload.price is not None and automatic and item.is_completed
    )
    if not requested:
        return
    if payment is not None and not automatic:
        # A manually entered payment remains controlled by the transaction editor.
        return
    if item.price <= 0:
        if automatic:
            payment.deleted_at = utc_now()
        return
    if payment is None:
        preferred = "Đi chợ" if item.plan.plan_type == "meal" else "Đi chơi"
        categories = db.query(Category).filter_by(archived=False).order_by(Category.id).all()
        category = next((c for c in categories if c.name == preferred), None)
        category = category or next((c for c in categories if c.name == "Khác"), None)
        category = category or next(iter(categories), None)
        if category is None:
            raise HTTPException(409, "Hãy thêm danh mục chi tiêu trước khi đánh dấu đã chi.")
        # Persist the origin in the existing opaque key. It survives archive
        # restore and cannot collide when SQLite reuses a deleted item ID.
        payment = Transaction(
            client_id=AUTO_PREFIX + str(uuid4()),
            source_item_id=item.id,
            title=item.name,
            amount=item.price,
            kind="expense",
            spent_on=today(),
            category_id=category.id,
            note="Ghi từ ô hoàn thành kế hoạch",
        )
        db.add(payment)
    elif payment.deleted_at is not None:
        payment.spent_on = today()
        payment.amount = item.price
    elif payload.price is not None:
        payment.amount = item.price
    # Repeating a checkbox request must preserve an actual amount/date edited
    # through the ledger after the original checkbox write was acknowledged.
    if payload.name is not None:
        payment.title = item.name
    payment.deleted_at = None
