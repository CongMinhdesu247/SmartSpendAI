"""Authentication settings, rate limiting, CSRF/Host/Body guards and CSP middleware."""

from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import os
import secrets
import threading
import time
from typing import Optional
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse
from pwdlib import PasswordHash
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from backend import database
from backend.auth_models import AccessSession, Account
from backend.tenancy import OWNER_ID

SESSION_DAYS = 30
MAX_SESSIONS_PER_USER = 10
MAX_API_BODY_BYTES = 256 * 1024
MAX_IMPORT_BODY_BYTES = 5 * 1024 * 1024
password_hasher = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH: Optional[str] = None


class _PayloadTooLargeError(Exception):
    """Raised when a streaming or chunked request body exceeds the configured byte limit."""


def get_dummy_password_hash() -> str:
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = password_hasher.hash("smartspend-constant-time-dummy-guard-2026")
    return _DUMMY_PASSWORD_HASH


def _make_bounded_receive(receive, max_bytes: int):
    received = 0

    async def bounded_receive():
        nonlocal received
        message = await receive()
        if message.get("type") == "http.request":
            chunk = message.get("body", b"") or b""
            received += len(chunk)
            if received > max_bytes:
                raise _PayloadTooLargeError()
        return message

    return bounded_receive


def normalize_allowed_host(raw_value: str) -> str:
    text = str(raw_value or "").strip().lower().rstrip("/")
    if not text:
        return ""
    if "://" in text:
        parsed = urlsplit(text)
        return parsed.netloc.lower()
    if "/" in text:
        text = text.split("/", 1)[0]
    return text


def cloud_mode():
    return database.is_cloud_mode()


def normalize_public_url(value):
    value = str(value or "").strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path
    ):
        raise ValueError("Địa chỉ app phải là HTTPS, không có đường dẫn hoặc thông tin đăng nhập")
    hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    host = f"[{hostname}]" if ":" in hostname else hostname
    port = parsed.port
    return "https://" + host + (f":{port}" if port and port != 443 else "")


def _is_safe_local_host(host_header: str) -> bool:
    if not host_header:
        return True
    try:
        hostname = (urlsplit("//" + host_header).hostname or "").lower()
    except ValueError:
        return False
    if hostname in ("localhost", "127.0.0.1", "::1", "testserver", ""):
        return True
    try:
        addr = ipaddress.ip_address(hostname)
        return addr.is_loopback or addr.is_private
    except ValueError:
        return False


_LOCAL_PROXY_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),  # Tailscale / CGNAT
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


def _is_local_or_lan_ip(addr) -> bool:
    return any(addr in net for net in _LOCAL_PROXY_NETWORKS)


def extract_client_ip(request, trust_proxy: bool = False, trusted_header: str = "auto") -> str:
    """Resolve real client IP safely behind local Reverse Proxy / Cloudflare Tunnel when trusted."""
    peer = request.client.host if getattr(request, "client", None) else ""
    if not trust_proxy or not peer:
        return peer or "unknown"
    try:
        peer_ip = ipaddress.ip_address(peer)
        if not _is_local_or_lan_ip(peer_ip):
            return peer
    except ValueError:
        return peer or "unknown"

    headers = getattr(request, "headers", {}) or {}
    mode = (trusted_header or "auto").strip().lower()
    if mode in ("x-real-ip", "cf-connecting-ip"):
        header_order = (mode,)
    elif mode == "x-forwarded-for":
        header_order = ()
    else:
        # Prefer X-Real-IP set by local Nginx/Caddy over client-spoofable CF-Connecting-IP;
        # fall back to CF-Connecting-IP when behind Cloudflare Tunnel (where X-Real-IP is absent).
        header_order = ("x-real-ip", "cf-connecting-ip")

    for header_name in header_order:
        candidate = headers.get(header_name, "").strip()
        if candidate:
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass

    xff = headers.get("x-forwarded-for", "")
    if xff:
        valid_ips = []
        for raw_part in xff.split(","):
            part = raw_part.strip()
            if not part:
                continue
            try:
                valid_ips.append(ipaddress.ip_address(part))
            except ValueError:
                continue
        for candidate_ip in reversed(valid_ips):
            if not _is_local_or_lan_ip(candidate_ip):
                return str(candidate_ip)
        if valid_ips:
            return str(valid_ips[0])

    return peer or "unknown"


@dataclass(frozen=True)
class AccessSettings:
    cloud: bool
    password_hash: str
    secret: str
    public_url: str = ""
    generated_secret: bool = False
    accounts: bool = False
    allow_registration: Optional[bool] = None
    invite_code: str = ""
    trust_proxy: bool = False
    trusted_header: str = "auto"
    allowed_hosts: tuple[str, ...] = ()

    @classmethod
    def from_environment(cls):
        invite = os.environ.get("SMARTSPEND_INVITE_CODE", "").strip()
        open_reg = os.environ.get("SMARTSPEND_ALLOW_REGISTRATION", "").lower() in ("1", "true")
        trust_proxy = os.environ.get("SMARTSPEND_TRUST_PROXY", "").lower() in ("1", "true")
        trusted_header = os.environ.get("SMARTSPEND_TRUSTED_HEADER", "auto").strip().lower() or "auto"
        extra_hosts = tuple(
            normalized
            for h in os.environ.get("SMARTSPEND_ALLOWED_HOSTS", "").split(",")
            if (normalized := normalize_allowed_host(h))
        )
        return cls(
            cloud=cloud_mode(),
            password_hash=os.environ.get("SMARTSPEND_PASSWORD_HASH", ""),
            secret=os.environ.get("SMARTSPEND_SESSION_SECRET", "") or secrets.token_urlsafe(48),
            public_url=normalize_public_url(
                os.environ.get("SMARTSPEND_PUBLIC_URL", "")
                or os.environ.get("RENDER_EXTERNAL_URL", "")
            ),
            generated_secret=not bool(os.environ.get("SMARTSPEND_SESSION_SECRET")),
            accounts=cloud_mode() or os.environ.get("SMARTSPEND_ACCOUNTS") == "1",
            allow_registration=open_reg or bool(invite),
            invite_code=invite,
            trust_proxy=trust_proxy,
            trusted_header=trusted_header,
            allowed_hosts=extra_hosts,
        )

    @property
    def required(self):
        return self.cloud or bool(self.password_hash)

    @property
    def can_register(self) -> bool:
        if not self.accounts:
            return False
        if self.allow_registration is None:
            return True
        return bool(self.allow_registration)

    @property
    def version(self):
        return hashlib.sha256(self.password_hash.encode()).hexdigest()

    def validate(self):
        if self.required:
            if not self.password_hash.startswith("$argon2id$") or len(self.secret) < 32:
                raise RuntimeError(
                    "Cần cấu hình SMARTSPEND_PASSWORD_HASH và SMARTSPEND_SESSION_SECRET trước khi chạy cloud"
                )
        if self.cloud:
            if self.generated_secret:
                raise RuntimeError("Cloud cần session secret cố định, không dùng khóa tạm")
            if not normalize_public_url(self.public_url):
                raise RuntimeError("Cloud cần SMARTSPEND_PUBLIC_URL hoặc RENDER_EXTERNAL_URL")


def loopback_admin(request):
    """Strictly requires direct loopback socket in non-cloud, single-owner desktop mode."""
    if cloud_mode() or getattr(getattr(request.app.state, "access", None), "accounts", False):
        return False
    try:
        return ipaddress.ip_address(request.client.host).is_loopback and request.url.hostname in (
            "localhost",
            "127.0.0.1",
            "::1",
            "testserver",
        )
    except (ValueError, AttributeError):
        return False


def session_key(sid):
    return hashlib.sha256(sid.encode()).hexdigest()


def password_version(value):
    return hashlib.sha256(value.encode()).hexdigest()


def authenticated(request, settings):
    request.state.user = None
    if not settings.required:
        request.state.user = {"id": OWNER_ID, "username": "chuso"}
        return True
    sid = request.session.get("sid")
    if not isinstance(sid, str) or len(sid) > 100 or database.engine is None:
        return False
    with Session(database.engine) as db:
        row = db.get(AccessSession, session_key(sid))
        if not row:
            return False
        expires = row.expires_at.replace(tzinfo=row.expires_at.tzinfo or timezone.utc)
        if settings.accounts:
            account = db.get(Account, row.user_id)
            if account:
                if not account.active:
                    return False
                version = password_version(account.password_hash)
                user = {"id": account.id, "username": account.username}
            elif row.user_id == OWNER_ID:
                version = settings.version
                user = {"id": OWNER_ID, "username": "chuso"}
            else:
                return False
        else:
            version = settings.version
            user = {"id": OWNER_ID, "username": "chuso"}
        if expires > datetime.now(timezone.utc) and hmac.compare_digest(
            row.password_version, version
        ):
            request.state.user = user
            return True
        return False


class LoginLimiter:
    """Bounded per-IP and per-(IP, account) login limits without penalizing valid logins."""

    def __init__(self):
        self.lock = threading.Lock()
        self.ip_attempts = OrderedDict()
        self.user_attempts = OrderedDict()

    @staticmethod
    def _prune_and_check(bucket_map, key, window_seconds, limit):
        now = time.monotonic()
        attempts = bucket_map.setdefault(key, deque())
        bucket_map.move_to_end(key)
        while attempts and now - attempts[0] > window_seconds:
            attempts.popleft()
        while len(bucket_map) > 4096:
            bucket_map.popitem(last=False)
        return len(attempts) < limit, attempts, now

    def allow(self, client_ip: str, username: str = "") -> bool:
        ip_key = client_ip or "unknown"
        acct_key = f"{ip_key}:{username.strip().lower()[:32]}"
        with self.lock:
            ip_ok, ip_deque, now = self._prune_and_check(self.ip_attempts, ip_key, 900, 16)
            acct_ok, acct_deque, _ = self._prune_and_check(self.user_attempts, acct_key, 900, 8)
            if not ip_ok or not acct_ok:
                return False
            ip_deque.append(now)
            acct_deque.append(now)
            return True

    def refund_success(self, client_ip: str, username: str = "") -> None:
        ip_key = client_ip or "unknown"
        acct_key = f"{ip_key}:{username.strip().lower()[:32]}"
        with self.lock:
            ip_deque = self.ip_attempts.get(ip_key)
            if ip_deque:
                ip_deque.pop()
            acct_deque = self.user_attempts.get(acct_key)
            if acct_deque:
                acct_deque.pop()


class AccessMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings):
        super().__init__(app)
        self.settings = settings

    def _allowed_cloud_origins(self) -> set[str]:
        origins = set()
        if self.settings.public_url:
            origins.add(self.settings.public_url.rstrip("/").lower())
        for host in self.settings.allowed_hosts:
            origins.add(f"https://{host}")
            origins.add(f"http://{host}")
        return origins

    async def dispatch(self, request, call_next):
        path = request.url.path
        is_api = path.startswith("/api/") or path == "/api"
        public = path in ("/api/auth/status", "/api/auth/login", "/api/auth/register")
        response = None

        if self.settings.cloud and path != "/healthz":
            expected_hosts = {
                urlsplit(self.settings.public_url).netloc.lower(),
                *self.settings.allowed_hosts,
            }
            if request.headers.get("host", "").lower() not in expected_hosts:
                response = JSONResponse({"detail": "Địa chỉ truy cập không hợp lệ"}, 400)
        elif not self.settings.cloud and path != "/healthz":
            if not _is_safe_local_host(request.headers.get("host", "")):
                response = JSONResponse({"detail": "Địa chỉ truy cập không hợp lệ"}, 400)

        if response is None and is_api and request.method not in ("GET", "HEAD", "OPTIONS"):
            max_bytes = (
                MAX_IMPORT_BODY_BYTES if path == "/api/finance/import" else MAX_API_BODY_BYTES
            )
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    if int(content_length) > max_bytes:
                        response = JSONResponse(
                            {"detail": "Dữ liệu gửi lên vượt quá giới hạn cho phép"}, 413
                        )
                except ValueError:
                    response = JSONResponse({"detail": "Header Content-Length không hợp lệ"}, 400)
            if response is None and hasattr(request, "_receive"):
                request._receive = _make_bounded_receive(request._receive, max_bytes)

        if response is None and is_api:
            try:
                request.state.authorized = await run_in_threadpool(
                    authenticated, request, self.settings
                )
            except SQLAlchemyError:
                response = JSONResponse({"detail": "Chưa kết nối được dữ liệu. Hãy thử lại."}, 503)
            if response is None and not public and not request.state.authorized:
                response = JSONResponse(
                    {"detail": "Vui lòng đăng nhập", "code": "LOGIN_REQUIRED"}, 401
                )
            if (
                response is None
                and not public
                and self.settings.accounts
                and request.state.authorized
            ):
                if request.headers.get("x-smartspend-user") != request.state.user["id"]:
                    response = JSONResponse(
                        {
                            "detail": "Tài khoản đã thay đổi. Hãy tải lại ứng dụng.",
                            "code": "ACCOUNT_CHANGED",
                        },
                        409,
                    )
            if response is None and request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin", "").rstrip("/").lower()
                fetch_site = request.headers.get("sec-fetch-site", "")
                if self.settings.required:
                    allowed_origins = self._allowed_cloud_origins() or {
                        str(request.base_url).rstrip("/").lower()
                    }
                    if (
                        (origin and origin not in allowed_origins)
                        or fetch_site == "cross-site"
                        or (not origin and request.headers.get("x-smartspend-client") != "1")
                    ):
                        response = JSONResponse({"detail": "Yêu cầu không đến từ app"}, 403)
                else:
                    expected_local = str(request.base_url).rstrip("/").lower()
                    if (origin and origin != expected_local) or fetch_site == "cross-site":
                        response = JSONResponse({"detail": "Yêu cầu không đến từ app"}, 403)

        if response is None:
            try:
                response = await call_next(request)
            except _PayloadTooLargeError:
                response = JSONResponse(
                    {"detail": "Dữ liệu gửi lên vượt quá giới hạn cho phép"}, 413
                )
        if is_api or path in ("/healthz", "/sw.js"):
            response.headers["Cache-Control"] = "no-store"
        elif path in ("/", "/index.html", "/manifest.json"):
            response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-SmartSpend-App"] = "1"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        if self.settings.cloud:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; object-src 'none'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; img-src 'self' data: blob:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response


def install_access(app, settings=None):
    from backend.routers.auth import build_auth_router

    settings = settings or AccessSettings.from_environment()
    app.state.access = settings
    app.state.login_limiter = LoginLimiter()
    app.state.password_slots = threading.BoundedSemaphore(2)
    app.add_middleware(AccessMiddleware, settings=settings)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret,
        session_cookie="smartspend_session",
        max_age=SESSION_DAYS * 86400,
        same_site="strict",
        https_only=settings.cloud,
    )
    app.include_router(build_auth_router(app, settings))
