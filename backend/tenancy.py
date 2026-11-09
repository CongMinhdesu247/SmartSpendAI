"""A request-scoped ledger identity, enforced by ORM and PostgreSQL RLS."""
from sqlalchemy import Column, String, event, text
from sqlalchemy.orm import Session, with_loader_criteria
from fastapi import HTTPException

OWNER_ID = "legacy-owner"
RUNTIME_ROLE = "smartspend_ledger"


class LedgerOwned:
    user_id = Column(String(36), nullable=False, default=OWNER_ID, index=True)


class LedgerSession(Session):
    def __init__(self, *args, user_id, **kwargs):
        super().__init__(*args, **kwargs)
        self.info["user_id"] = user_id

    def get(self, entity, ident, **kwargs):
        # These natural keys repeat in every person's ledger.
        if entity.__tablename__ in ("spend_preferences", "spend_budgets") and not isinstance(ident, (tuple, dict)):
            ident = (self.info["user_id"], ident)
        row = super().get(entity, ident, **kwargs)
        if isinstance(row, LedgerOwned) and row.user_id != self.info["user_id"]:
            return None
        return row


@event.listens_for(LedgerSession, "do_orm_execute")
def scope_statement(state):
    if state.is_select or state.is_update or state.is_delete:
        user_id = state.session.info["user_id"]
        state.statement = state.statement.options(with_loader_criteria(
            LedgerOwned, lambda cls: cls.user_id == user_id, include_aliases=True))


@event.listens_for(LedgerSession, "before_flush")
def scope_writes(db, _context, _instances):
    from backend.models import Plan, PlanItem
    from backend.finance_models import Category, RecurringBill, Goal, Transaction, Contribution, Budget, PlanArchive
    links = {PlanItem: {"plan_id": Plan}, RecurringBill: {"category_id": Category},
             Transaction: {"category_id": Category, "source_item_id": PlanItem, "recurring_id": RecurringBill},
             Contribution: {"goal_id": Goal}, Budget: {"category_id": Category},
             PlanArchive: {"restored_plan_id": Plan}}
    user_id = db.info["user_id"]
    for row in list(db.new) + list(db.dirty) + list(db.deleted):
        if not isinstance(row, LedgerOwned):
            raise RuntimeError("Only ledger rows may be written through a LedgerSession")
        if row in db.new and row.user_id is None:
            row.user_id = user_id
        if row.user_id != user_id:
            raise HTTPException(404, "Không tìm thấy dữ liệu")
        for key, target in links.get(type(row), {}).items():
            ident = getattr(row, key)
            if ident is not None and db.get(target, ident) is None:
                raise HTTPException(404, "Không tìm thấy dữ liệu liên kết")


@event.listens_for(LedgerSession, "after_begin")
def postgres_identity(db, _transaction, connection):
    if connection.dialect.name == "postgresql":
        # An unprivileged role is essential: the Supabase postgres owner bypasses RLS.
        connection.execute(text("SET LOCAL ROLE smartspend_ledger"))
        connection.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": db.info["user_id"]})
