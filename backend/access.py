"""Single-owner cloud login. No API/database secrets are sent to the browser."""
import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.concurrency import run_in_threadpool

from backend import database
from backend.finance_models import AccessSession

SESSION_DAYS = 30
password_hasher = PasswordHash.recommended()


def cloud_mode():
    return database.is_cloud_mode()


def normalize_public_url(value):
    value = str(value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path):
        raise ValueError("Địa chỉ app phải là HTTPS, không có đường dẫn hoặc thông tin đăng nhập")
    hostname = parsed.hostname.encode('idna').decode('ascii').lower()
    host = f'[{hostname}]' if ':' in hostname else hostname
    port = parsed.port
    return 'https://' + host + (f':{port}' if port and port != 443 else '')


@dataclass(frozen=True)
class AccessSettings:
    cloud: bool
    password_hash: str
    secret: str
    public_url: str = ""
    generated_secret: bool = False

    @classmethod
    def from_environment(cls):
        return cls(cloud_mode(), os.environ.get("SMARTSPEND_PASSWORD_HASH", ""),
                   os.environ.get("SMARTSPEND_SESSION_SECRET", "") or secrets.token_urlsafe(48),
                   normalize_public_url(os.environ.get("SMARTSPEND_PUBLIC_URL", "") or os.environ.get("RENDER_EXTERNAL_URL", "")),
                   not bool(os.environ.get("SMARTSPEND_SESSION_SECRET")))

    @property
    def required(self):
        return self.cloud or bool(self.password_hash)

    @property
    def version(self):
        return hashlib.sha256(self.password_hash.encode()).hexdigest()

    def validate(self):
        if self.required:
            if not self.password_hash.startswith("$argon2id$") or len(self.secret) < 32:
                raise RuntimeError("Cần cấu hình SMARTSPEND_PASSWORD_HASH và SMARTSPEND_SESSION_SECRET trước khi chạy cloud")
        if self.cloud:
            if self.generated_secret:
                raise RuntimeError("Cloud cần session secret cố định, không dùng khóa tạm")
            if not normalize_public_url(self.public_url):
                raise RuntimeError("Cloud cần SMARTSPEND_PUBLIC_URL hoặc RENDER_EXTERNAL_URL")


def loopback_admin(request):
    if cloud_mode():
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback and request.url.hostname in ("localhost", "127.0.0.1", "::1")
    except (ValueError, AttributeError):
        return False


def session_key(sid):
    return hashlib.sha256(sid.encode()).hexdigest()


def authenticated(request, settings):
    if not settings.required:
        return True
    sid = request.session.get("sid")
    if not isinstance(sid, str) or len(sid) > 100 or database.engine is None:
        return False
    with Session(database.engine) as db:
        row = db.get(AccessSession, session_key(sid))
        if not row:
            return False
        expires = row.expires_at.replace(tzinfo=row.expires_at.tzinfo or timezone.utc)
        return expires > datetime.now(timezone.utc) and hmac.compare_digest(row.password_version, settings.version)


class LoginLimiter:
    """Bounded per-process login limits; deployed with one worker."""
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = OrderedDict()
        self.global_attempts = deque()

    def allow(self, key):
        now = time.monotonic()
        with self.lock:
            while self.global_attempts and now - self.global_attempts[0] > 60:
                self.global_attempts.popleft()
            attempts = self.clients.setdefault(key, deque())
            self.clients.move_to_end(key)
            while attempts and now - attempts[0] > 900:
                attempts.popleft()
            if len(self.global_attempts) >= 30 or len(attempts) >= 8:
                return False
            attempts.append(now)
            self.global_attempts.append(now)
            while len(self.clients) > 4096:
                self.clients.popitem(last=False)
            return True


class AccessMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request, call_next):
        path = request.url.path
        is_api = path.startswith("/api/") or path == "/api"
        public = path in ("/api/auth/status", "/api/auth/login")
        response = None
        if self.settings.cloud and path != "/healthz":
            expected_host = urlsplit(self.settings.public_url).netloc.lower()
            if request.headers.get("host", "").lower() != expected_host:
                response = JSONResponse({"detail": "Địa chỉ truy cập không hợp lệ"}, 400)
        if response is None and is_api:
            try:
                request.state.authorized = await run_in_threadpool(authenticated, request, self.settings)
            except SQLAlchemyError:
                response = JSONResponse({"detail": "Chưa kết nối được dữ liệu. Hãy thử lại."}, 503)
            if response is None and not public and not request.state.authorized:
                response = JSONResponse({"detail": "Vui lòng đăng nhập", "code": "LOGIN_REQUIRED"}, 401)
            if response is None and request.method not in ("GET", "HEAD", "OPTIONS") and self.settings.required:
                origin = request.headers.get("origin", "").rstrip("/")
                expected = self.settings.public_url.rstrip("/") or str(request.base_url).rstrip("/")
                if ((origin and origin != expected) or request.headers.get("sec-fetch-site") == "cross-site"
                        or (not origin and request.headers.get("x-smartspend-client") != "1")):
                    response = JSONResponse({"detail": "Yêu cầu không đến từ app"}, 403)
        if response is None:
            response = await call_next(request)
        if is_api or path in ("/healthz", "/sw.js"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-SmartSpend-App"] = "1"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response


class LoginInput(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def install_access(app, settings=None):
    settings = settings or AccessSettings.from_environment()
    app.state.access = settings
    app.state.login_limiter = LoginLimiter()
    app.state.password_slots = threading.BoundedSemaphore(2)
    app.add_middleware(AccessMiddleware, settings=settings)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret, session_cookie="smartspend_session",
                       max_age=SESSION_DAYS * 86400, same_site="strict", https_only=settings.cloud)
    router = APIRouter(prefix="/api/auth", tags=["Access"])

    @router.get("/status")
    def status(request: Request):
        return {"required": settings.required, "authenticated": request.state.authorized,
                "cloud": settings.cloud, "can_edit_config": not settings.cloud and loopback_admin(request)}

    @router.post("/login")
    def login(payload: LoginInput, request: Request):
        if not settings.required:
            return {"authenticated": True}
        if not app.state.login_limiter.allow(request.client.host if request.client else "unknown"):
            raise HTTPException(429, "Đã thử đăng nhập nhiều lần. Hãy đợi 15 phút rồi thử lại.")
        if not app.state.password_slots.acquire(blocking=False):
            raise HTTPException(429, "Máy chủ đang bận. Hãy thử lại sau.")
        try:
            try:
                valid = password_hasher.verify(payload.password, settings.password_hash)
            except Exception:
                valid = False
        finally:
            app.state.password_slots.release()
        if not valid:
            raise HTTPException(401, "Mật khẩu chưa đúng")
        now = datetime.now(timezone.utc)
        sid = secrets.token_urlsafe(32)
        with Session(database.engine) as db:
            db.execute(delete(AccessSession).where(AccessSession.expires_at <= now))
            prior = request.session.get("sid")
            if isinstance(prior, str):
                db.execute(delete(AccessSession).where(AccessSession.id == session_key(prior)))
            db.add(AccessSession(id=session_key(sid), password_version=settings.version,
                                 expires_at=now + timedelta(days=SESSION_DAYS)))
            db.commit()
        request.session.clear()
        request.session["sid"] = sid
        return {"authenticated": True}

    @router.post("/logout")
    def logout(request: Request):
        sid = request.session.get("sid")
        if isinstance(sid, str) and database.engine is not None:
            with Session(database.engine) as db:
                db.execute(delete(AccessSession).where(AccessSession.id == session_key(sid)))
                db.commit()
        request.session.clear()
        return {"success": True}

    @router.post("/logout-all")
    def logout_all(request: Request):
        with Session(database.engine) as db:
            db.execute(delete(AccessSession))
            db.commit()
        request.session.clear()
        return {"success": True}

    app.include_router(router)
