"""AI and manual spending plans router: CRUD, checklist sync, copy, trash & replacement."""

from datetime import datetime
import json
import logging
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import database, models
from backend.ai_limits import ai_slot
from backend.finance_api import preferences as read_preferences
from backend.finance_models import PlanArchive, Transaction
from backend.plan_payments import AUTO_PREFIX, sync_completion_payment
from backend.schemas.plans import (
    CreatePlanItemRequest,
    CreatePlanRequest,
    GeneratePlanRequest,
    PatchItemRequest,
    ReplaceItemRequest,
    UpdatePlanRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Plans"])


def recalculate_plan_totals(db: Session, plan: models.Plan) -> None:
    """Tính lại tổng chi phí dự kiến (`estimated_cost`) của `Plan` từ các `PlanItem`."""
    items = db.query(models.PlanItem).filter(models.PlanItem.plan_id == plan.id).all()
    estimated = sum(max(0, int(item.price or 0)) for item in items)
    if estimated > 2_000_000_000:
        raise HTTPException(422, "Tổng giá dự kiến của kế hoạch không được vượt 2 tỷ đồng")
    plan.estimated_cost = estimated
    db.add(plan)


@router.post("/api/plans/generate")
def api_generate_plan(
    payload: GeneratePlanRequest,
    db: Session = Depends(database.get_db),
    _ai=Depends(ai_slot),
) -> Dict[str, Any]:
    """Gọi Gemini AI tạo kế hoạch chi tiêu và lưu vào cơ sở dữ liệu."""
    from backend import api_server

    try:
        saved = read_preferences(db)
        personal_preferences = "\n".join(
            filter(
                None,
                [
                    payload.preferences,
                    f"Khẩu vị: {saved['tastes']}" if saved["tastes"] else "",
                    f"Tránh: {saved['avoid']}" if saved["avoid"] else "",
                    f"Nguyên liệu đã có, không mua lại: {payload.pantry}" if payload.pantry else "",
                ],
            )
        )
        db.rollback()  # Do not hold a DB transaction during a network AI call.
        ai_result = api_server.generate_smart_plan(
            plan_type=payload.plan_type,
            total_budget=payload.total_budget,
            region=payload.region,
            days_or_people=payload.days_or_people,
            preferences=personal_preferences,
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.error("AI plan generation failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502, detail="Chưa gọi được AI. Kiểm tra API key và thử lại."
        )

    try:
        custom_title = (payload.title or "").strip()
        final_title = custom_title if custom_title else ai_result["title"]

        new_plan = models.Plan(
            title=final_title,
            plan_type=ai_result["plan_type"],
            total_budget=ai_result["total_budget"],
            estimated_cost=ai_result["estimated_cost"],
            actual_spent=0,
            region=ai_result["region"],
            advice=ai_result["advice"],
        )
        db.add(new_plan)
        db.flush()

        for item_data in ai_result["items"]:
            plan_item = models.PlanItem(
                plan_id=new_plan.id,
                category=item_data["category"],
                time_or_day=item_data["time_or_day"],
                name=item_data["name"],
                details=item_data["details"],
                price=item_data["price"],
                is_completed=bool(item_data.get("is_completed", False)),
            )
            db.add(plan_item)

        db.commit()
        db.refresh(new_plan)
        return new_plan.to_dict(include_items=True)
    except Exception as db_exc:
        db.rollback()
        logger.error("Saving AI plan failed (%s)", type(db_exc).__name__)
        raise HTTPException(status_code=500, detail="Chưa lưu được kế hoạch. Hãy thử lại.")


@router.post("/api/plans")
def create_manual_plan(
    payload: CreatePlanRequest,
    db: Session = Depends(database.get_db),
) -> Dict[str, Any]:
    """Tạo một kế hoạch thủ công không cần gọi AI."""
    plan = models.Plan(
        title=payload.title,
        plan_type=payload.plan_type,
        total_budget=payload.total_budget,
        estimated_cost=0,
        actual_spent=0,
        region=payload.region,
        advice=payload.advice,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan.to_dict(include_items=True)


@router.get("/api/plans")
def list_plans(
    plan_type: Optional[str] = None,
    before_id: Annotated[Optional[int], Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    db: Session = Depends(database.get_db),
) -> List[Dict[str, Any]]:
    """Bounded pages, ordered by creation time and ID; before_id is the last row."""
    query = db.query(models.Plan)
    if plan_type in ("meal", "hangout"):
        query = query.filter(models.Plan.plan_type == plan_type)

    if before_id is not None:
        anchor = db.get(models.Plan, before_id)
        if not anchor:
            raise HTTPException(409, "Danh sách vừa thay đổi. Hãy tải lại kế hoạch.")
        query = query.filter(
            or_(
                models.Plan.created_at < anchor.created_at,
                and_(models.Plan.created_at == anchor.created_at, models.Plan.id < anchor.id),
            )
        )
    plans = query.order_by(models.Plan.created_at.desc(), models.Plan.id.desc()).limit(limit).all()
    return [plan.to_dict(include_items=True) for plan in plans]


@router.get("/api/plans/{plan_id}")
def get_plan_detail(
    plan_id: int,
    db: Session = Depends(database.get_db),
) -> Dict[str, Any]:
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy kế hoạch yêu cầu.")
    return plan.to_dict(include_items=True)


@router.patch("/api/plans/{plan_id}")
def update_plan(
    plan_id: int,
    payload: UpdatePlanRequest,
    db: Session = Depends(database.get_db),
) -> Dict[str, Any]:
    """Cập nhật tên, ngân sách, khu vực hoặc ghi chú lời khuyên của kế hoạch."""
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy kế hoạch.")
    if payload.title is not None:
        plan.title = payload.title
    if payload.total_budget is not None:
        plan.total_budget = payload.total_budget
    if payload.region is not None:
        plan.region = payload.region
    if payload.advice is not None:
        plan.advice = payload.advice
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan.to_dict(include_items=True)


@router.post("/api/plans/{plan_id}/items")
def add_plan_item(
    plan_id: int,
    payload: CreatePlanItemRequest,
    db: Session = Depends(database.get_db),
) -> Dict[str, Any]:
    """Thêm thủ công một hạng mục mới vào kế hoạch."""
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy kế hoạch.")
    category = "activity" if plan.plan_type == "hangout" else payload.category
    if plan.plan_type == "meal" and category not in ("grocery", "daily_menu"):
        category = "grocery"
    item = models.PlanItem(
        plan_id=plan.id,
        category=category,
        time_or_day=payload.time_or_day,
        name=payload.name,
        details=payload.details,
        price=payload.price,
        is_completed=False,
    )
    db.add(item)
    db.flush()
    recalculate_plan_totals(db, plan)
    db.commit()
    db.expire_all()
    refreshed = db.get(models.Plan, plan_id)
    return {"item": item.to_dict(), "plan": refreshed.to_dict(include_items=True)}


@router.patch("/api/items/{item_id}")
def update_plan_item(
    item_id: int,
    payload: PatchItemRequest,
    request: Request = None,
    db: Session = Depends(database.get_db),
) -> Dict[str, Any]:
    from backend.finance_api import client_today

    item = db.query(models.PlanItem).filter(models.PlanItem.id == item_id).with_for_update().first()
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy hạng mục chi tiêu này.")

    if payload.is_completed is not None:
        item.is_completed = bool(payload.is_completed)
    if payload.price is not None:
        item.price = max(0, int(payload.price))
    if payload.name is not None and payload.name.strip():
        item.name = payload.name.strip()
    if payload.details is not None:
        item.details = payload.details.strip()
    if payload.time_or_day is not None:
        item.time_or_day = payload.time_or_day.strip()

    sync_completion_payment(db, item, payload, spent_on=client_today(request))
    db.add(item)
    db.flush()

    plan = db.query(models.Plan).filter(models.Plan.id == item.plan_id).first()
    if not plan:
        db.commit()
        return {"item": item.to_dict()}

    recalculate_plan_totals(db, plan)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Hạng mục vừa thay đổi. Hãy tải lại và thử lại.") from None
    db.expire_all()

    return {
        "item": item.to_dict(),
        "plan": plan.to_dict(include_items=True),
    }


@router.delete("/api/items/{item_id}")
def delete_plan_item(
    item_id: int,
    db: Session = Depends(database.get_db),
) -> Dict[str, Any]:
    """Xóa một hạng mục khỏi kế hoạch; tự động hủy khoản chi do checkbox tạo nếu có."""
    item = db.query(models.PlanItem).filter(models.PlanItem.id == item_id).with_for_update().first()
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy hạng mục.")
    plan_id = item.plan_id
    for payment in item.payments:
        if payment.deleted_at is None and payment.client_id.startswith(AUTO_PREFIX):
            payment.deleted_at = models.utc_now()
    db.delete(item)
    db.flush()
    plan = db.get(models.Plan, plan_id)
    if plan:
        recalculate_plan_totals(db, plan)
    db.commit()
    db.expire_all()
    updated_plan = db.get(models.Plan, plan_id)
    return {
        "success": True,
        "plan": updated_plan.to_dict(include_items=True) if updated_plan else None,
    }


@router.delete("/api/plans/{plan_id}")
def delete_plan(
    plan_id: int,
    delete_auto_payments: Annotated[bool, Query()] = False,
    db: Session = Depends(database.get_db),
) -> Dict[str, Any]:
    """Lưu trữ bản chụp kế hoạch vào thùng rác và xóa kế hoạch."""
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy kế hoạch cần xóa.")

    snapshot = plan.to_dict()
    now = models.utc_now()
    for serialized, item in zip(snapshot["items"], plan.items):
        serialized["payment_ids"] = [payment.id for payment in item.payments]
        auto_deleted_ids = []
        if delete_auto_payments:
            for payment in item.payments:
                if payment.deleted_at is None and payment.client_id.startswith(AUTO_PREFIX):
                    payment.deleted_at = now
                    auto_deleted_ids.append(payment.id)
        serialized["auto_deleted_payment_ids"] = auto_deleted_ids
    archived = PlanArchive(snapshot=json.dumps(snapshot, ensure_ascii=False))
    db.add(archived)
    db.delete(plan)
    db.commit()
    return {
        "success": True,
        "deleted_id": plan_id,
        "undo_id": archived.id,
        "message": "Đã chuyển kế hoạch vào thùng rác.",
    }


@router.post("/api/plans/trash/{archive_id}/restore")
def restore_plan(archive_id: int, db: Session = Depends(database.get_db)):
    archived = db.query(PlanArchive).filter_by(id=archive_id).with_for_update().first()
    if not archived:
        raise HTTPException(404, "Không tìm thấy bản lưu kế hoạch")
    if archived.restored:
        plan = db.get(models.Plan, archived.restored_plan_id) if archived.restored_plan_id else None
        if plan:
            return plan.to_dict()
        raise HTTPException(409, "Bản lưu này đã được khôi phục trước đó")
    claimed = (
        db.query(PlanArchive)
        .filter_by(id=archive_id, restored=False)
        .update({"restored": True}, synchronize_session=False)
    )
    if not claimed:
        db.rollback()
        db.expire_all()
        archived = db.get(PlanArchive, archive_id)
        plan = (
            db.get(models.Plan, archived.restored_plan_id)
            if archived and archived.restored_plan_id
            else None
        )
        if plan:
            return plan.to_dict()
        raise HTTPException(409, "Kế hoạch vừa được khôi phục. Hãy tải lại danh sách.")
    snapshot = json.loads(archived.snapshot)
    plan = models.Plan(
        **{
            key: snapshot[key]
            for key in ("title", "plan_type", "total_budget", "estimated_cost", "region", "advice")
        },
        actual_spent=0,
    )
    if snapshot.get("created_at"):
        plan.created_at = datetime.fromisoformat(snapshot["created_at"])
    plan.items = [
        models.PlanItem(
            **{
                key: item[key]
                for key in ("category", "time_or_day", "name", "details", "price", "is_completed")
            }
        )
        for item in snapshot["items"]
    ]
    db.add(plan)
    db.flush()
    for saved, item in zip(snapshot["items"], plan.items):
        auto_deleted = set(saved.get("auto_deleted_payment_ids", []))
        for payment_id in saved.get("payment_ids", []):
            payment = db.get(Transaction, payment_id)
            if payment and payment.source_item_id is None:
                payment.source_item_id = item.id
                if payment_id in auto_deleted and payment.deleted_at is not None:
                    payment.deleted_at = None
    archived.restored = True
    archived.restored_plan_id = plan.id
    db.commit()
    db.expire_all()
    return plan.to_dict()


@router.delete("/api/plans/trash/{archive_id}")
def purge_archived_plan(archive_id: int, db: Session = Depends(database.get_db)):
    archived = db.get(PlanArchive, archive_id)
    if not archived:
        raise HTTPException(404, "Không tìm thấy bản lưu kế hoạch")
    db.delete(archived)
    db.commit()
    return {"success": True}


@router.post("/api/plans/{plan_id}/copy")
def copy_plan(plan_id: int, db: Session = Depends(database.get_db)):
    original = db.get(models.Plan, plan_id)
    if not original:
        raise HTTPException(404, "Không tìm thấy kế hoạch")
    duplicate = models.Plan(
        title=(original.title[:240] + " (bản sao)"),
        plan_type=original.plan_type,
        total_budget=original.total_budget,
        estimated_cost=original.estimated_cost,
        actual_spent=0,
        region=original.region,
        advice=original.advice,
    )
    duplicate.items = [
        models.PlanItem(
            category=i.category,
            time_or_day=i.time_or_day,
            name=i.name,
            details=i.details,
            price=i.price,
            is_completed=False,
        )
        for i in original.items
    ]
    db.add(duplicate)
    db.commit()
    return duplicate.to_dict()


@router.post("/api/items/{item_id}/replace")
def replace_item(
    item_id: int,
    payload: ReplaceItemRequest,
    db: Session = Depends(database.get_db),
    _ai=Depends(ai_slot),
):
    from backend import api_server

    item = db.get(models.PlanItem, item_id)
    if not item:
        raise HTTPException(404, "Không tìm thấy hạng mục")
    if item.paid_amount:
        raise HTTPException(409, "Mục đã thanh toán không thể đổi bằng AI")
    plan = item.plan
    old = (item.name, item.details, item.price, item.is_completed)
    other_cost = sum(i.price for i in plan.items if i.id != item.id)
    budget = max(0, plan.total_budget - other_cost)
    context = {
        "category": item.category,
        "name": item.name,
        "details": item.details,
        "region": plan.region,
        "budget": budget,
        "preferences": payload.preferences,
        "personal": read_preferences(db),
        "time_or_day": item.time_or_day,
    }
    db.rollback()
    try:
        replacement = api_server.suggest_replacement(context)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("AI item replacement failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Chưa đổi được mục bằng AI. Hãy thử lại.")
    db.expire_all()
    item = db.query(models.PlanItem).filter_by(id=item_id).with_for_update().first()
    if (
        not item
        or (item.name, item.details, item.price, item.is_completed) != old
        or item.paid_amount
    ):
        raise HTTPException(409, "Hạng mục vừa thay đổi. Hãy tải lại trước khi đổi.")
    other_cost = sum(i.price for i in item.plan.items if i.id != item_id)
    if other_cost + replacement["price"] > item.plan.total_budget:
        raise HTTPException(409, "Phương án mới vượt ngân sách hiện tại")
    item.name = replacement["name"]
    item.details = replacement["details"]
    item.price = replacement["price"]
    item.is_completed = False
    db.flush()
    recalculate_plan_totals(db, item.plan)
    db.commit()
    return {"plan": item.plan.to_dict()}
