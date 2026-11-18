"""Financial health scoring, end-of-month burn-rate projection, goal pacing, and multi-month trends."""

import calendar
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.finance_models import Goal, RecurringBill, Transaction


def compute_health_score(
    *,
    income_val: int,
    expense_val: int,
    budget: Optional[int],
    elapsed_days: int,
    days_in_month: int,
    no_spend_days: int,
    mom_expense_pct: Optional[float],
    overdue_bills: int,
    tx_count: int,
) -> Dict[str, Any]:
    """Compute a transparent 0-100 personal financial health score with 4-pillar breakdown."""
    if tx_count == 0 and budget is None and overdue_bills == 0:
        return {
            "score": 78,
            "grade": "Sẵn sàng",
            "tone": "indigo",
            "summary": "Đặt ngân sách tháng và ghi giao dịch đầu tiên để kích hoạt chấm điểm chuyên sâu.",
            "pillars": [
                {"label": "Kỷ luật ngân sách", "score": 28, "max": 40},
                {"label": "Tiết kiệm ròng", "score": 22, "max": 30},
                {"label": "Hóa đơn đúng hạn", "score": 15, "max": 15},
                {"label": "Nhịp chi ổn định", "score": 13, "max": 15},
            ],
        }

    # 1. Budget discipline & pacing (0-40)
    if budget is None:
        budget_pts = 24
    elif budget == 0:
        budget_pts = 40 if expense_val == 0 else 4
    else:
        ratio = expense_val / budget
        pace = max(1, elapsed_days) / max(1, days_in_month)
        if expense_val <= budget:
            if ratio <= pace + 0.08:
                budget_pts = max(33, 40 - int(max(0.0, ratio - pace) * 30))
            else:
                budget_pts = max(20, int(36 - (ratio - pace) * 35))
        else:
            over_ratio = min(1.0, (expense_val - budget) / budget)
            budget_pts = max(0, int(16 - over_ratio * 16))

    # 2. Net cashflow & savings rate (0-30)
    if income_val > 0:
        sr = (income_val - expense_val) / income_val
        if sr >= 0.25:
            savings_pts = 30
        elif sr >= 0.12:
            savings_pts = 24
        elif sr >= 0:
            savings_pts = 17
        else:
            savings_pts = max(0, int(12 + sr * 20))
    else:
        savings_pts = 22 if (budget is not None and expense_val <= budget) else 18

    # 3. Recurring bill timeliness (0-15)
    if overdue_bills == 0:
        bill_pts = 15
    elif overdue_bills == 1:
        bill_pts = 7
    else:
        bill_pts = 0

    # 4. Consistency & MoM trend (0-15)
    habit_pts = 10
    if mom_expense_pct is not None:
        if mom_expense_pct <= 0:
            habit_pts += 3
        elif mom_expense_pct > 25:
            habit_pts -= 4
    if elapsed_days >= 3 and (no_spend_days / elapsed_days) >= 0.2:
        habit_pts += 2
    habit_pts = max(0, min(15, habit_pts))

    score = max(0, min(100, budget_pts + savings_pts + bill_pts + habit_pts))
    if score >= 85:
        grade, tone = "Xuất sắc", "green"
        summary = "Nhịp chi tiêu rất kỷ luật và cân đối tốt với kế hoạch tháng."
    elif score >= 70:
        grade, tone = "Tốt", "sky"
        summary = (
            "Tài chính ổn định. Hãy đặt hạn mức tháng để tối ưu điểm tối đa."
            if budget is None
            else "Dòng tiền đang nằm trong vùng kiểm soát an toàn."
        )
    elif score >= 50:
        grade, tone = "Cần chú ý", "orange"
        summary = (
            f"Có {overdue_bills} hóa đơn định kỳ quá hạn cần xử lý sớm."
            if overdue_bills
            else "Tốc độ chi tiêu đang nhanh hơn nhịp ngày trong tháng."
        )
    else:
        grade, tone = "Báo động", "rose"
        summary = "Chi tiêu đã vượt ngưỡng an toàn; nên ưu tiên nhu cầu thiết yếu."

    return {
        "score": score,
        "grade": grade,
        "tone": tone,
        "summary": summary,
        "pillars": [
            {"label": "Kỷ luật ngân sách", "score": budget_pts, "max": 40},
            {"label": "Tiết kiệm ròng", "score": savings_pts, "max": 30},
            {"label": "Hóa đơn đúng hạn", "score": bill_pts, "max": 15},
            {"label": "Nhịp chi ổn định", "score": habit_pts, "max": 15},
        ],
    }


def compute_month_projection(
    *,
    expense_val: int,
    budget: Optional[int],
    observed_days: int,
    days_in_month: int,
    days_left: int,
) -> Dict[str, Any]:
    """Forecast end-of-month total expense based on observed daily burn rate."""
    if observed_days <= 0:
        projected = 0
    elif days_left == 0:
        projected = expense_val
    else:
        projected = round((expense_val / observed_days) * days_in_month)

    projected_remaining = (budget - projected) if budget is not None else None
    if budget is None or budget <= 0 or observed_days == 0:
        pace_status = "untracked"
    elif projected <= budget * 0.92:
        pace_status = "under_pace"
    elif projected <= budget * 1.03:
        pace_status = "on_track"
    else:
        pace_status = "over_pace"

    return {
        "projected_expense": int(projected),
        "projected_remaining": int(projected_remaining) if projected_remaining is not None else None,
        "pace_status": pace_status,
    }


def compute_goal_pace(goal: Goal, saved: int, current_day: date) -> Dict[str, Any]:
    """Calculate remaining amount and required monthly saving pace to hit goal deadline."""
    remaining = max(0, int(goal.target) - int(saved))
    completed = remaining == 0
    days_left: Optional[int] = None
    monthly_needed: Optional[int] = None
    if goal.deadline:
        days_left = (goal.deadline - current_day).days
        if remaining > 0 and days_left > 0:
            months_equiv = max(1.0, days_left / 30.4375)
            monthly_needed = round(remaining / months_equiv)
        elif remaining > 0 and days_left <= 0:
            monthly_needed = remaining
    return {
        "remaining": remaining,
        "completed": completed,
        "days_left": days_left,
        "monthly_needed": monthly_needed,
    }


def compute_recurring_monthly_equivalent(bills: List[RecurringBill]) -> int:
    """Normalize weekly/monthly/yearly recurring bills into estimated monthly commitment."""
    total = 0.0
    for b in bills:
        amt = float(b.amount or 0)
        if b.frequency == "weekly":
            total += amt * 52.0 / 12.0
        elif b.frequency == "yearly":
            total += amt / 12.0
        else:
            total += amt
    return round(total)


def shift_month(year: int, month: int, delta: int) -> date:
    idx = (year * 12 + (month - 1)) + delta
    y, m = divmod(idx, 12)
    return date(max(1970, min(2200, y)), m + 1, 1)


def compute_monthly_trends(db: Session, end_month_start: date, months: int = 6) -> Dict[str, Any]:
    """Build portable multi-month income, expense, net cashflow & savings-rate series."""
    count = max(2, min(12, int(months)))
    first_start = shift_month(end_month_start.year, end_month_start.month, -(count - 1))
    after_end = shift_month(end_month_start.year, end_month_start.month, 1)

    rows = (
        db.query(Transaction.spent_on, Transaction.kind, Transaction.amount)
        .filter(
            Transaction.deleted_at.is_(None),
            Transaction.spent_on >= first_start,
            Transaction.spent_on < after_end,
        )
        .all()
    )

    buckets: Dict[str, Dict[str, int]] = {}
    for idx in range(count):
        m_date = shift_month(first_start.year, first_start.month, idx)
        buckets[m_date.strftime("%Y-%m")] = {"income": 0, "expense": 0}

    for spent_on, kind, amount in rows:
        key = spent_on.strftime("%Y-%m")
        if key in buckets:
            buckets[key]["income" if kind == "income" else "expense"] += int(amount or 0)

    series = []
    for ym, vals in buckets.items():
        inc = vals["income"]
        exp = vals["expense"]
        net = inc - exp
        y_str, m_str = ym.split("-")
        series.append(
            {
                "month": ym,
                "label": f"T{int(m_str)}/{y_str[-2:]}",
                "income": inc,
                "expense": exp,
                "net": net,
                "savings_rate": round((net / inc) * 100) if inc > 0 else None,
            }
        )

    active_expenses = [item["expense"] for item in series if item["expense"] > 0]
    avg_expense = round(sum(active_expenses) / len(active_expenses)) if active_expenses else 0
    total_net = sum(item["net"] for item in series)
    days_last = calendar.monthrange(end_month_start.year, end_month_start.month)[1]

    return {
        "months": count,
        "end_month": end_month_start.strftime("%Y-%m"),
        "days_in_end_month": days_last,
        "average_monthly_expense": avg_expense,
        "cumulative_net_savings": total_net,
        "series": series,
    }
