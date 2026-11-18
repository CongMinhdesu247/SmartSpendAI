"""System configuration, LAN discovery, QR generation and health endpoints."""

import io
import socket
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from backend import database
from backend.access import loopback_admin, normalize_public_url
from backend.schemas.plans import ConfigUpdateRequest

router = APIRouter(tags=["System"])


def get_lan_ip() -> str:
    """Tìm địa chỉ IPv4 LAN của máy tính trong mạng Wi-Fi nội bộ."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
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


@router.get("/api/config")
def get_config(request: Request) -> Dict[str, Any]:
    """Đọc cấu hình hiện tại và trạng thái kết nối Database."""
    cfg = database.load_config()
    db_status = database.get_db_status()
    api_key = cfg.get("gemini_api_key", "")
    can_edit = loopback_admin(request)
    if not can_edit:
        return {
            "has_api_key": bool(api_key),
            "has_database_url": bool(cfg.get("database_url")),
            "can_edit_config": False,
            "cloud_mode": database.is_cloud_mode(),
            "db_status": {"is_cloud_postgres": db_status["is_cloud_postgres"]},
        }
    masked_key = (
        f"{api_key[:6]}...{api_key[-4:]}" if len(api_key) > 10 else ("Đã nhập" if api_key else "")
    )
    return {
        "gemini_api_key_masked": masked_key,
        "has_api_key": bool(api_key),
        "has_database_url": bool(cfg.get("database_url", "")),
        "cloud_url": cfg.get("cloud_url", ""),
        "allow_lan": bool(cfg.get("allow_lan", False)),
        "can_edit_config": can_edit,
        "cloud_mode": database.is_cloud_mode(),
        "db_status": db_status,
    }


@router.post("/api/config")
def update_config(payload: ConfigUpdateRequest, request: Request) -> Dict[str, Any]:
    """Lưu cấu hình hệ thống trên máy chủ cục bộ và kiểm tra kết nối Database."""
    if not loopback_admin(request):
        raise HTTPException(
            403, "Cấu hình hosting được quản lý trên máy tính hoặc bảng điều khiển hosting"
        )
    if request.headers.get("origin") and request.headers["origin"].rstrip("/") != str(
        request.base_url
    ).rstrip("/"):
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
    new_cloud_url = (
        payload.cloud_url.strip()
        if payload.cloud_url is not None
        else current_cfg.get("cloud_url", "")
    )
    new_allow_lan = (
        bool(payload.allow_lan)
        if payload.allow_lan is not None
        else bool(current_cfg.get("allow_lan", False))
    )

    if payload.clear_api_key:
        new_api_key = ""
    if payload.clear_database_url:
        new_db_url = ""
    if payload.clear_cloud_url:
        new_cloud_url = ""

    if new_cloud_url:
        try:
            new_cloud_url = normalize_public_url(new_cloud_url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    next_cfg = {
        "gemini_api_key": new_api_key,
        "database_url": new_db_url,
        "cloud_url": new_cloud_url,
        "allow_lan": new_allow_lan,
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
        "cloud_url": new_cloud_url,
        "allow_lan": new_allow_lan,
    }


@router.get("/api/network-info")
def get_network_info(request: Request) -> Dict[str, Any]:
    """Trả về thông tin địa chỉ mở ứng dụng trên iPhone (HTTPS Cloud hoặc Wi-Fi LAN)."""
    cfg = database.load_config()
    lan_ip = get_lan_ip()
    port = request.url.port or 8000
    lan_url = f"http://{lan_ip}:{port}"
    configured = cfg.get("cloud_url", "")
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
        "allow_lan": bool(cfg.get("allow_lan", False)),
        "cloud_mode": database.is_cloud_mode(),
        "db_mode": database.current_db_mode,
        "instructions": (
            "Kết nối iPhone cùng mạng Wi-Fi với máy tính, mở trình duyệt Safari truy cập địa chỉ "
            f"{lan_url} rồi nhấn 'Chia sẻ -> Thêm vào Màn hình chính' để cài đặt App."
        ),
    }


@router.get("/api/network-qr")
def network_qr(request: Request):
    import qrcode
    from qrcode.image.svg import SvgPathImage

    info = get_network_info(request)
    image = qrcode.make(info["app_url"], image_factory=SvgPathImage, border=3)
    stream = io.BytesIO()
    image.save(stream)
    return Response(
        stream.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"}
    )


@router.get("/healthz")
def health():
    if database.engine is not None:
        try:
            from sqlalchemy import text

            with database.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            from fastapi.responses import JSONResponse

            return JSONResponse({"status": "degraded", "detail": "Database unreachable"}, 503)
    return {
        "status": "ok",
        "db": database.current_db_mode if database.engine is not None else "ready",
    }
