"""Data validation schemas for finance."""

from datetime import date
from typing import Annotated, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

MONEY_MAX = 9_000_000_000_000


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
    color: Literal[
        "orange", "green", "violet", "sky", "indigo", "pink", "teal", "blue", "slate"
    ] = "indigo"


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


class EditTransactionInput(TransactionInput):
    # Server-created checklist payments have an opaque origin key. New manual
    # transactions still accept UUIDs only, so clients cannot claim this origin.
    client_id: (
        UUID
        | Annotated[
            str,
            Field(
                pattern=r"^plan-completion:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
            ),
        ]
    )


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


class ImportTransactionItem(BaseModel):
    client_id: Optional[str] = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=255)
    amount: int = Field(gt=0, le=MONEY_MAX, strict=True)
    kind: Literal["expense", "income"] = "expense"
    spent_on: date
    category_name: str = Field(default="Khác", max_length=80)
    category_color: Literal[
        "orange", "green", "violet", "sky", "indigo", "pink", "teal", "blue", "slate"
    ] = "indigo"
    note: str = Field(default="", max_length=2000)

    @field_validator("title")
    @classmethod
    def trim_import_title(cls, value):
        if not value.strip():
            raise ValueError("Nội dung không được để trống")
        return value.strip()


class ImportCategoryItem(Named):
    name: str = Field(min_length=1, max_length=80)
    color: Literal[
        "orange", "green", "violet", "sky", "indigo", "pink", "teal", "blue", "slate"
    ] = "indigo"
    archived: bool = False


class ImportBudgetItem(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: int = Field(ge=0, le=MONEY_MAX, strict=True)
    category_name: Optional[str] = Field(default=None, max_length=80)


class ImportBillItem(Named):
    amount: int = Field(gt=0, le=MONEY_MAX, strict=True)
    category_name: str = Field(default="Khác", max_length=80)
    next_due: date
    frequency: Literal["weekly", "monthly", "yearly"] = "monthly"
    archived: bool = False


class ImportContributionItem(BaseModel):
    client_id: Optional[str] = Field(default=None, max_length=80)
    amount: int = Field(gt=0, le=MONEY_MAX, strict=True)
    saved_on: date


class ImportGoalItem(Named):
    target: int = Field(gt=0, le=MONEY_MAX, strict=True)
    deadline: Optional[date] = None
    archived: bool = False
    contributions: List[ImportContributionItem] = Field(default_factory=list, max_length=1000)


class ImportPlanSubItem(BaseModel):
    category: Literal["grocery", "daily_menu", "activity"] = "grocery"
    time_or_day: str = Field(default="", max_length=120)
    name: str = Field(min_length=1, max_length=255)
    details: str = Field(default="", max_length=5000)
    price: int = Field(default=0, ge=0, le=2_000_000_000)
    is_completed: bool = False


class ImportPlanItem(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    plan_type: Literal["meal", "hangout"] = "meal"
    total_budget: int = Field(ge=10000, le=2_000_000_000)
    estimated_cost: int = Field(default=0, ge=0, le=2_000_000_000)
    region: str = Field(default="Việt Nam", max_length=120)
    advice: str = Field(default="", max_length=5000)
    created_at: Optional[str] = Field(default=None, max_length=64)
    items: List[ImportPlanSubItem] = Field(default_factory=list, max_length=200)


class ImportLedgerInput(BaseModel):
    version: int = Field(default=1, ge=1, le=2)
    categories: List[ImportCategoryItem] = Field(default_factory=list, max_length=200)
    transactions: List[ImportTransactionItem] = Field(default_factory=list, max_length=5000)
    budgets: List[ImportBudgetItem] = Field(default_factory=list, max_length=500)
    recurring_bills: List[ImportBillItem] = Field(default_factory=list, max_length=200)
    goals: List[ImportGoalItem] = Field(default_factory=list, max_length=200)
    plans: List[ImportPlanItem] = Field(default_factory=list, max_length=200)
    preferences: Optional[PreferencesInput] = None


class AIReviewInput(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    focus: str = Field(default="", max_length=500)

