"""Additive finance schema. Money is stored as whole VND, never floating point."""
import unicodedata
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Column, Date, DateTime,
                        DDL, ForeignKey, Index, Integer, String, Text, UniqueConstraint, event)
from backend.database import Base
from backend.tenancy import LedgerOwned, OWNER_ID
from backend.models import utc_now

ID = BigInteger().with_variant(Integer, "sqlite")


def normalize_search(value):
    value = str(value).casefold().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


class Category(LedgerOwned, Base):
    __tablename__ = "spend_categories"
    id = Column(ID, primary_key=True, autoincrement=True)
    name = Column(String(80), nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    color = Column(String(20), nullable=False, default="indigo")
    archived = Column(Boolean, nullable=False, default=False)


class RecurringBill(LedgerOwned, Base):
    __tablename__ = "spend_recurring"
    id = Column(ID, primary_key=True, autoincrement=True)
    name = Column(String(160), nullable=False)
    amount = Column(BigInteger, nullable=False)
    category_id = Column(ID, ForeignKey("spend_categories.id"), nullable=False, index=True)
    next_due = Column(Date, nullable=False, index=True)
    frequency = Column(String(12), nullable=False, default="monthly")
    anchor_day = Column(Integer, nullable=False)
    archived = Column(Boolean, nullable=False, default=False)
    __table_args__ = (CheckConstraint("amount > 0 AND amount <= 9000000000000"),
                      CheckConstraint("frequency IN ('weekly','monthly','yearly')"),
                      CheckConstraint("anchor_day BETWEEN 1 AND 31"))


class Transaction(LedgerOwned, Base):
    __tablename__ = "spend_transactions"
    id = Column(ID, primary_key=True, autoincrement=True)
    client_id = Column(String(80), nullable=False)
    title = Column(String(255), nullable=False)
    search_title = Column(Text, nullable=False, default="")
    amount = Column(BigInteger, nullable=False)
    kind = Column(String(10), nullable=False, default="expense")
    spent_on = Column(Date, nullable=False)
    category_id = Column(ID, ForeignKey("spend_categories.id"), nullable=False, index=True)
    note = Column(Text, nullable=False, default="")
    source_item_id = Column(Integer, ForeignKey("plan_items.id", ondelete="SET NULL"), unique=True)
    recurring_id = Column(ID, ForeignKey("spend_recurring.id"), nullable=True, index=True)
    occurrence_on = Column(Date, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    __table_args__ = (CheckConstraint("amount > 0 AND amount <= 9000000000000"),
                      CheckConstraint("kind IN ('expense','income')"),
                      UniqueConstraint("recurring_id", "occurrence_on"),
                      UniqueConstraint("user_id", "client_id"),
                      Index("ix_spend_transaction_month", "spent_on", "id"))


class Budget(LedgerOwned, Base):
    __tablename__ = "spend_budgets"
    user_id = Column(String(36), primary_key=True, default=OWNER_ID)
    key = Column(String(60), primary_key=True)
    month = Column(Date, nullable=False, index=True)
    category_id = Column(ID, ForeignKey("spend_categories.id"), nullable=True, index=True)
    amount = Column(BigInteger, nullable=False)
    __table_args__ = (CheckConstraint("amount >= 0 AND amount <= 9000000000000"),)


class Goal(LedgerOwned, Base):
    __tablename__ = "spend_goals"
    id = Column(ID, primary_key=True, autoincrement=True)
    name = Column(String(160), nullable=False)
    target = Column(BigInteger, nullable=False)
    deadline = Column(Date, nullable=True)
    archived = Column(Boolean, nullable=False, default=False)
    __table_args__ = (CheckConstraint("target > 0 AND target <= 9000000000000"),)


class Contribution(LedgerOwned, Base):
    __tablename__ = "spend_contributions"
    id = Column(ID, primary_key=True, autoincrement=True)
    client_id = Column(String(80), nullable=False)
    goal_id = Column(ID, ForeignKey("spend_goals.id"), nullable=False, index=True)
    amount = Column(BigInteger, nullable=False)
    saved_on = Column(Date, nullable=False)
    __table_args__ = (UniqueConstraint("user_id", "client_id"), CheckConstraint("amount > 0 AND amount <= 9000000000000"),)


class Preference(LedgerOwned, Base):
    __tablename__ = "spend_preferences"
    user_id = Column(String(36), primary_key=True, default=OWNER_ID)
    key = Column(String(50), primary_key=True)
    value = Column(Text, nullable=False, default="")


class PlanArchive(LedgerOwned, Base):
    __tablename__ = "spend_plan_archive"
    id = Column(ID, primary_key=True, autoincrement=True)
    snapshot = Column(Text, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    restored = Column(Boolean, nullable=False, default=False)
    restored_plan_id = Column(Integer, ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True)


class Account(Base):
    __tablename__ = "spend_accounts"
    id = Column(String(36), primary_key=True)
    username = Column(String(32), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class AccessSession(Base):
    __tablename__ = "spend_access_sessions"
    id = Column(String(64), primary_key=True)  # SHA-256 of a random session ID
    user_id = Column(String(36), nullable=False, default=OWNER_ID, index=True)
    password_version = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


@event.listens_for(Transaction, "before_insert")
@event.listens_for(Transaction, "before_update")
def update_search_title(_mapper, _connection, transaction):
    transaction.search_title = normalize_search(transaction.title)


# Personal app: database owner accesses these through FastAPI. No direct browser
# Data API grants/policies; RLS denies anon/authenticated access to new tables.
for model in (Category, RecurringBill, Transaction, Budget, Goal, Contribution, Preference, PlanArchive, AccessSession, Account):
    event.listen(model.__table__, "after_create", DDL(
        'ALTER TABLE %(fullname)s ENABLE ROW LEVEL SECURITY'
    ).execute_if(dialect="postgresql"))
