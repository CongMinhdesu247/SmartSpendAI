from datetime import datetime, timezone
from typing import List

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, relationship

from backend.database import Base
from backend.tenancy import LedgerOwned


def utc_now() -> datetime:
    """Trả về thời gian hiện tại (UTC)."""
    return datetime.now(timezone.utc)


class Plan(LedgerOwned, Base):
    """
    Bảng `plans`: Lưu trữ thông tin tổng quan của một kế hoạch chi tiêu
    (Thực đơn đi chợ cả tuần hoặc Kế hoạch đi chơi/hẹn hò).
    """

    __tablename__ = "plans"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title: Mapped[str] = Column(String(255), nullable=False, index=True)
    plan_type: Mapped[str] = Column(String(50), nullable=False, index=True)  # "meal" hoặc "hangout"
    total_budget: Mapped[int] = Column(Integer, nullable=False)
    estimated_cost: Mapped[int] = Column(Integer, nullable=False, default=0)
    actual_spent: Mapped[int] = Column(Integer, nullable=False, default=0)
    region: Mapped[str] = Column(String(120), nullable=False, default="Việt Nam")
    advice: Mapped[str] = Column(Text, nullable=True, default="")
    created_at: Mapped[datetime] = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Quan hệ 1-nhiều với bảng plan_items, tự động xóa các item con khi xóa Plan
    items: Mapped[List["PlanItem"]] = relationship(
        "PlanItem",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PlanItem.id.asc()",
        lazy="selectin",
    )

    def to_dict(self, include_items: bool = True) -> dict:
        """Chuyển đổi đối tượng Plan sang dictionary phục vụ JSON response."""
        data = {
            "id": self.id,
            "title": self.title,
            "plan_type": self.plan_type,
            "total_budget": self.total_budget,
            "estimated_cost": self.estimated_cost,
            "actual_spent": sum(item.paid_amount for item in self.items),
            "unrecorded_legacy_spent": (self.actual_spent or 0) if not any(item.payments for item in self.items) else 0,
            "region": self.region,
            "advice": self.advice or "",
            "created_at": self.created_at.replace(tzinfo=self.created_at.tzinfo or timezone.utc).isoformat() if self.created_at else None,
        }
        if include_items:
            data["items"] = [item.to_dict() for item in (self.items or [])]
        else:
            data["items_count"] = len(self.items) if self.items is not None else 0
            data["completed_count"] = (
                sum(1 for item in self.items if item.is_completed)
                if self.items is not None
                else 0
            )
        return data


class PlanItem(LedgerOwned, Base):
    """
    Bảng `plan_items`: Lưu trữ từng hạng mục trong kế hoạch.
    - category = "grocery": Danh sách nguyên liệu cần mua gộp khi đi chợ
    - category = "daily_menu": Thực đơn Sáng - Trưa - Tối theo từng ngày
    - category = "activity": Lịch trình hoạt động đi chơi theo khung giờ
    """

    __tablename__ = "plan_items"

    id: Mapped[int] = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plan_id: Mapped[int] = Column(
        Integer,
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = Column(
        String(50),
        nullable=False,
        index=True,
        default="grocery",  # "grocery" | "daily_menu" | "activity"
    )
    time_or_day: Mapped[str] = Column(String(120), nullable=False, default="")
    name: Mapped[str] = Column(String(255), nullable=False)
    details: Mapped[str] = Column(Text, nullable=True, default="")
    price: Mapped[int] = Column(Integer, nullable=False, default=0)
    is_completed: Mapped[bool] = Column(Boolean, default=False, nullable=False)

    plan: Mapped["Plan"] = relationship("Plan", back_populates="items")
    payments = relationship("Transaction", lazy="selectin", passive_deletes=True)

    @property
    def paid_amount(self):
        return sum(payment.amount for payment in self.payments if payment.deleted_at is None)

    def to_dict(self) -> dict:
        """Chuyển đổi đối tượng PlanItem sang dictionary phục vụ JSON response."""
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "category": self.category,
            "time_or_day": self.time_or_day,
            "name": self.name,
            "details": self.details or "",
            "price": self.price,
            "is_completed": bool(self.is_completed),
            "payment": next(({
                "id": p.id, "amount": p.amount, "spent_on": p.spent_on.isoformat()
            } for p in self.payments if p.deleted_at is None), None),
        }

