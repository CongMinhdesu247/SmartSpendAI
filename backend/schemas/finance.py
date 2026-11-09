"""Data validation schemas for finance."""

from datetime import date
from typing import Annotated, Literal, Optional
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
