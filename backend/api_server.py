import socket
import json
import sys
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import database, models
from backend.ai_service import generate_smart_plan, suggest_replacement
from backend.finance_api import router as finance_router, initialize_finance, preferences as read_preferences
from backend.finance_models import Transaction, PlanArchive
from backend.ai_limits import ai_slot
from backend.plan_payments import sync_completion_payment
from backend.access import install_access, loopback_admin, normalize_public_url

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    FRONTEND_DIR = Path(sys._MEIPASS) / "frontend"
else:
    FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# =====================================================================
# PYDANTIC REQUEST SCHEMAS CHO REST API
# =====================================================================
logger = logging.getLogger(__name__)


class TrimmedInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ConfigUpdateRequest(BaseModel):
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API Key")
    database_url: Optional[str] = Field(
        default=None,
        description="Chuỗi kết nối Supabase PostgreSQL (postgresql://... hoặc postgres://...)",
    )
    clear_api_key: bool = False
    clear_database_url: bool = False


class GeneratePlanRequest(TrimmedInput):
    title: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Tên kế hoạch tùy chọn do người dùng đặt (nếu để trống AI sẽ tự đặt)",
    )
    plan_type: Literal["meal", "hangout"] = Field(
        default="meal",
        description="Loại kế hoạch: 'meal' (Thực đơn & đi chợ) hoặc 'hangout' (Đi chơi & hẹn hò)",
    )
    total_budget: int = Field(
        default=500000,
        ge=10000,
        le=2000000000,
        description="Ngân sách tối đa (VNĐ)",
    )
    region: str = Field(default="TP. Hồ Chí Minh", min_length=1, max_length=120, description="Khu vực / Thành phố")
    days_or_people: str = Field(
        default="7 ngày cho 1-2 người",
        min_length=1, max_length=120,
        description="Thời lượng hoặc số lượng người tham gia",
    )
    preferences: str = Field(
        default="",
        max_length=2000,
        description="Sở thích, khẩu vị, hình thức hoặc yêu cầu đặc biệt",
    )
    pantry: str = Field(default="", max_length=2000)


class PatchItemRequest(TrimmedInput):
    is_completed: Optional[bool] = Field(
        default=None,
        description="Trạng thái đã mua / đã chi tiêu",
    )
    price: Optional[int] = Field(
        default=None,
        ge=0,
        le=2000000000,
        description="Giá tiền thực tế chỉnh sửa (VNĐ)",
    )
    name: Optional[str] = Field(default=None, min_length=1, max_length=255, description="Tên mục (tùy chọn chỉnh sửa)")
    details: Optional[str] = Field(default=None, max_length=5000, description="Chi tiết mục (tùy chọn chỉnh sửa)")


# =====================================================================
# HÀM TIỆN ÍCH LẤY ĐỊA CHỈ IP LAN CHO TRUY CẬP IPHONE PWA
# =====================================================================
def get_lan_ip() -> str:
    """Tìm địa chỉ IPv4 LAN của máy tính trong mạng Wi-Fi nội bộ."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            # Kết nối giả lập tới DNS công cộng để xác định interface mạng chính
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        for addr in socket.gethostbyname_ex(hostname)[2]:
            if not addr.startswith("127."):
                return addr
    except Exception:
        pass

    return "127.0.0.1"


def recalculate_plan_totals(db: Session, plan: models.Plan) -> None:
    """
    Tính toán lại tổng chi phí dự kiến (`estimated_cost`) và tổng chi tiêu thực tế (`actual_spent`)
    của `Plan` dựa trên toàn bộ `PlanItem` hiện có.
    """
    items = (
        db.query(models.PlanItem)
        .filter(models.PlanItem.plan_id == plan.id)
        .all()
    )
    estimated = sum(max(0, int(item.price or 0)) for item in items)
    if estimated > 2_000_000_000:
        raise HTTPException(422, "Tổng giá dự kiến của kế hoạch không được vượt 2 tỷ đồng")
    plan.estimated_cost = estimated
    # The existing actual_spent column is legacy. API totals now derive from the
    # bigint ledger, without overwriting historic columns or narrowing amounts.
    db.add(plan)


# =====================================================================
# KHỞI TẠO ỨNG DỤNG FASTAPI
# =====================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo kết nối Database (Supabase PostgreSQL hoặc fallback SQLite) khi server bật."""
    app.state.access.validate()
    database.init_db_connection()
    initialize_finance(database.engine)
    yield


app = FastAPI(
    title="SmartSpend Pro API",
    description="API Quản lý tài chính, Lên thực đơn đi chợ & Kế hoạch đi chơi bằng AI đồng bộ Supabase PostgreSQL.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if database.is_cloud_mode() else "/docs",
    redoc_url=None if database.is_cloud_mode() else "/redoc",
    openapi_url=None if database.is_cloud_mode() else "/openapi.json",
)

install_access(app)
app.include_router(finance_router)


# =====================================================================
# 1. ENDPOINTS QUẢN LÝ CẤU HÌNH & KẾT NỐI SUPABASE POSTGRESQL
# =====================================================================
@app.get("/api/config")
def get_config(request: Request) -> Dict[str, Any]:
    """Đọc cấu hình hiện tại và trạng thái kết nối Database."""
    cfg = database.load_config()
    db_status = database.get_db_status()
    api_key = cfg.get("gemini_api_key", "")
    can_edit = loopback_admin(request)
    if not can_edit:
        return {"has_api_key": bool(api_key), "has_database_url": bool(cfg.get("database_url")),
                "can_edit_config": False, "cloud_mode": database.is_cloud_mode(),
                "db_status": {"is_cloud_postgres": db_status["is_cloud_postgres"]}}
    masked_key = (
        f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else ("Đã nhập" if api_key else "")
    )
    return {
        "gemini_api_key_masked": masked_key,
        "has_api_key": bool(api_key),
        "has_database_url": bool(cfg.get("database_url", "")),
        "can_edit_config": can_edit,
        "cloud_mode": database.is_cloud_mode(),
        "db_status": db_status,
    }


@app.post("/api/config")
def update_config(payload: ConfigUpdateRequest, request: Request) -> Dict[str, Any]:
    """
    Lưu `gemini_api_key` và `database_url` (PostgreSQL URI),
    đồng thời tự động re-init kết nối Database và chạy `Base.metadata.create_all` lên Supabase.
    """
    if not loopback_admin(request):
        raise HTTPException(403, "Cấu hình hosting được quản lý trên máy tính hoặc bảng điều khiển hosting")
    if request.headers.get("origin") and request.headers["origin"].rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Yêu cầu không đến từ app")
    current_cfg = database.load_config()

    new_api_key = (
        payload.gemini_api_key.strip()
        if payload.gemini_api_key is not None
        else current_cfg.get("gemini_api_key", "")
    )
    new_db_url = (
        database.normalize_database_url(payload.database_url)
        if payload.database_url is not None
        else current_cfg.get("database_url", "")
    )
    if payload.clear_api_key:
        new_api_key = ""
    if payload.clear_database_url:
        new_db_url = ""

    next_cfg = {
        "gemini_api_key": new_api_key,
        "database_url": new_db_url,
        "cloud_url": current_cfg.get("cloud_url", ""),
    }
    try:
        conn_result = database.init_db_connection(custom_url=new_db_url, config_to_save=next_cfg)
    except database.DatabaseConnectionError as exc:
        raise HTTPException(503, str(exc)) from None

    return {
        "success": True,
        "connection": conn_result,
        "db_status": database.get_db_status(),
        "has_api_key": bool(new_api_key),
    }


# =====================================================================
# 2. ENDPOINT THÔNG TIN MẠNG LAN CHO IPHONE / PWA
# =====================================================================
@app.get("/api/network-info")
def get_network_info(request: Request) -> Dict[str, Any]:
    """
    Trả về địa chỉ IP LAN của máy tính (VD: http://192.168.1.x:8000)
    để người dùng quét mã QR hoặc nhập lên Safari iPhone truy cập ngay lập tức.
    """
    lan_ip = get_lan_ip()
    port = request.url.port or 8000
    lan_url = f"http://{lan_ip}:{port}"
    configured = database.load_config().get("cloud_url", "")
    try:
        public_url = normalize_public_url(configured)
    except ValueError:
        public_url = ""
    return {
        "ip": lan_ip,
        "port": port,
        "lan_url": lan_url,
        "public_url": public_url,
        "app_url": public_url or lan_url,
        "cloud_mode": database.is_cloud_mode(),
        "db_mode": database.current_db_mode,
        "instructions": (
            "Kết nối iPhone cùng mạng Wi-Fi với máy tính, mở trình duyệt Safari truy cập địa chỉ "
            f"{lan_url} rồi nhấn 'Chia sẻ -> Thêm vào Màn hình chính' để cài đặt App."
        ),
    }


@app.get("/api/network-qr")
def network_qr(request: Request):
    import io
    import qrcode
    from qrcode.image.svg import SvgPathImage
    info = get_network_info(request)
    image = qrcode.make(info["app_url"], image_factory=SvgPathImage, border=3)
    stream = io.BytesIO()
    image.save(stream)
    return Response(stream.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/healthz")
def health():
    return {"status": "ok"}


# =====================================================================
# 3. ENDPOINTS QUẢN LÝ KẾ HOẠCH (PLANS & PLAN ITEMS)
# =====================================================================
@app.post("/api/plans/generate")
def api_generate_plan(
    payload: GeneratePlanRequest,
    db: Session = Depends(database.get_db),
    _ai=Depends(ai_slot),
) -> Dict[str, Any]:
    """Gọi Gemini AI tạo kế hoạch chi tiêu -> Lưu vào Database -> Trả về JSON chi tiết."""
    try:
        saved = read_preferences(db)
        personal_preferences = "\n".join(filter(None, [payload.preferences,
            f"Khẩu vị: {saved['tastes']}" if saved['tastes'] else "",
            f"Tránh: {saved['avoid']}" if saved['avoid'] else "",
            f"Nguyên liệu đã có, không mua lại: {payload.pantry}" if payload.pantry else ""]))
        db.rollback()  # Do not hold a DB transaction during a network AI call.
        ai_result = generate_smart_plan(
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
        raise HTTPException(status_code=502, detail="Chưa gọi được AI. Kiểm tra API key và thử lại.")

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
        db.flush()  # Lấy new_plan.id trước khi thêm các PlanItem

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
        raise HTTPException(
            status_code=500,
            detail="Chưa lưu được kế hoạch. Hãy thử lại.",
        )


@app.get("/api/plans")
def list_plans(
    plan_type: Optional[str] = None,
    before_id: Optional[int] = Query(None, gt=0),
    limit: int = Query(30, ge=1, le=100),
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
        query = query.filter(or_(models.Plan.created_at < anchor.created_at,
            and_(models.Plan.created_at == anchor.created_at, models.Plan.id < anchor.id)))
    plans = query.order_by(models.Plan.created_at.desc(), models.Plan.id.desc()).limit(limit).all()
    return [plan.to_dict(include_items=True) for plan in plans]


@app.get("/api/plans/{plan_id}")
def get_plan_detail(
    plan_id: int,
    db: Session = Depends(database.get_db),
) -> Dict[str, Any]:
    """Lấy chi tiết 1 kế hoạch kèm toàn bộ `items`."""
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy kế hoạch yêu cầu.")
    return plan.to_dict(include_items=True)


@app.patch("/api/items/{item_id}")
def update_plan_item(
    item_id: int,
    payload: PatchItemRequest,
    db: Session = Depends(database.get_db),
) -> Dict[str, Any]:
    """
    Tick/bỏ tick `is_completed` VÀ/HOẶC sửa lại giá tiền thực tế (`price`),
    sau đó tự động tính lại tổng `actual_spent` và `estimated_cost` của `Plan` trong Database.
    """
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

    # Persist the checklist and its automatic expense in the same transaction.
    sync_completion_payment(db, item, payload)
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


@app.delete("/api/plans/{plan_id}")
def delete_plan(
    plan_id: int,
    db: Session = Depends(database.get_db),
) -> Dict[str, Any]:
    """Xóa kế hoạch và toàn bộ các hạng mục con khỏi Database."""
    plan = db.query(models.Plan).filter(models.Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy kế hoạch cần xóa.")

    snapshot = plan.to_dict()
    for serialized, item in zip(snapshot["items"], plan.items):
        serialized["payment_ids"] = [payment.id for payment in item.payments]
    archived = PlanArchive(snapshot=json.dumps(snapshot, ensure_ascii=False))
    db.add(archived)
    db.delete(plan)
    db.commit()
    return {
        "success": True,
        "deleted_id": plan_id,
        "undo_id": archived.id,
        "message": "Đã xóa kế hoạch thành công.",
    }


# =====================================================================
# PHỤC VỤ GIAO DIỆN WEB DASHBOARD & PWA (MOUNT FRONTEND STATIC FILES)
# =====================================================================
@app.post("/api/plans/trash/{archive_id}/restore")
def restore_plan(archive_id: int, db: Session = Depends(database.get_db)):
    archived = db.query(PlanArchive).filter_by(id=archive_id).with_for_update().first()
    if not archived:
        raise HTTPException(404, "Không tìm thấy bản lưu kế hoạch")
    if archived.restored:
        plan = db.get(models.Plan, archived.restored_plan_id) if archived.restored_plan_id else None
        if plan:
            return plan.to_dict()
        raise HTTPException(409, "Bản lưu này đã được khôi phục trước đó")
    # Atomic claim also serializes retries on SQLite, where FOR UPDATE is ignored.
    claimed = db.query(PlanArchive).filter_by(id=archive_id, restored=False).update(
        {"restored": True}, synchronize_session=False)
    if not claimed:
        db.rollback()
        db.expire_all()
        archived = db.get(PlanArchive, archive_id)
        plan = db.get(models.Plan, archived.restored_plan_id) if archived and archived.restored_plan_id else None
        if plan:
            return plan.to_dict()
        raise HTTPException(409, "Kế hoạch vừa được khôi phục. Hãy tải lại danh sách.")
    snapshot = json.loads(archived.snapshot)
    plan = models.Plan(**{key: snapshot[key] for key in ("title", "plan_type", "total_budget", "estimated_cost", "region", "advice")}, actual_spent=0)
    if snapshot.get("created_at"):
        plan.created_at = datetime.fromisoformat(snapshot["created_at"])
    plan.items = [models.PlanItem(**{key: item[key] for key in ("category", "time_or_day", "name", "details", "price", "is_completed")}) for item in snapshot["items"]]
    db.add(plan)
    db.flush()
    for saved, item in zip(snapshot["items"], plan.items):
        for payment_id in saved.get("payment_ids", []):
            payment = db.get(Transaction, payment_id)
            if payment and payment.source_item_id is None:
                payment.source_item_id = item.id
    archived.restored = True
    archived.restored_plan_id = plan.id
    db.commit()
    db.expire_all()
    return plan.to_dict()


@app.post("/api/plans/{plan_id}/copy")
def copy_plan(plan_id: int, db: Session = Depends(database.get_db)):
    original = db.get(models.Plan, plan_id)
    if not original:
        raise HTTPException(404, "Không tìm thấy kế hoạch")
    duplicate = models.Plan(title=(original.title[:240] + " (bản sao)"), plan_type=original.plan_type,
        total_budget=original.total_budget, estimated_cost=original.estimated_cost,
        actual_spent=0, region=original.region, advice=original.advice)
    duplicate.items = [models.PlanItem(category=i.category, time_or_day=i.time_or_day,
        name=i.name, details=i.details, price=i.price, is_completed=False) for i in original.items]
    db.add(duplicate)
    db.commit()
    return duplicate.to_dict()


class ReplaceItemRequest(TrimmedInput):
    preferences: str = Field(default="", max_length=2000)


@app.post("/api/items/{item_id}/replace")
def replace_item(item_id: int, payload: ReplaceItemRequest, db: Session = Depends(database.get_db), _ai=Depends(ai_slot)):
    item = db.get(models.PlanItem, item_id)
    if not item:
        raise HTTPException(404, "Không tìm thấy hạng mục")
    if item.paid_amount:
        raise HTTPException(409, "Mục đã thanh toán không thể đổi bằng AI")
    plan = item.plan
    old = (item.name, item.details, item.price, item.is_completed)
    other_cost = sum(i.price for i in plan.items if i.id != item.id)
    budget = max(0, plan.total_budget - other_cost)
    context = {"category": item.category, "name": item.name, "details": item.details,
               "region": plan.region, "budget": budget, "preferences": payload.preferences,
               "personal": read_preferences(db), "time_or_day": item.time_or_day}
    db.rollback()
    try:
        replacement = suggest_replacement(context)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.error("AI item replacement failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Chưa đổi được mục bằng AI. Hãy thử lại.")
    db.expire_all()
    item = db.query(models.PlanItem).filter_by(id=item_id).with_for_update().first()
    if not item or (item.name, item.details, item.price, item.is_completed) != old or item.paid_amount:
        raise HTTPException(409, "Hạng mục vừa thay đổi. Hãy tải lại trước khi đổi.")
    # Check the whole plan again after AI returns, in case another item changed.
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


@app.get("/")
def serve_root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(
        {
            "app": "SmartSpend Pro API",
            "status": "running",
            "db_mode": database.current_db_mode,
            "docs_url": "/docs",
        }
    )


if FRONTEND_DIR.exists():
    app.mount(
        "/frontend",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend_assets",
    )
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend_root",
    )

