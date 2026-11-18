"""Authentication & private-ledger account routes (/api/auth/*)."""

from datetime import datetime, timedelta, timezone
import hmac
import secrets
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import database
from backend.auth_models import AccessSession, Account
from backend.finance_models import Category, Preference
from backend.schemas.access import ChangePasswordInput, LoginInput, RegisterInput
from backend.tenancy import OWNER_ID


def build_auth_router(app, settings) -> APIRouter:
    from backend.access import (
        MAX_SESSIONS_PER_USER,
        SESSION_DAYS,
        extract_client_ip,
        get_dummy_password_hash,
        loopback_admin,
        password_hasher,
        password_version,
        session_key,
    )

    dummy_hash = get_dummy_password_hash()
    router = APIRouter(prefix="/api/auth", tags=["Access"])

    @router.get("/status")
    def status(request: Request):
        return {
            "required": settings.required,
            "authenticated": request.state.authorized,
            "cloud": settings.cloud,
            "accounts": settings.accounts,
            "can_register": settings.can_register,
            "invite_required": bool(settings.invite_code),
            "can_change_password": settings.required and settings.accounts,
            "user": getattr(request.state, "user", None),
            "can_edit_config": not settings.cloud and loopback_admin(request),
        }

    def check_attempt(request: Request, username: str = "") -> str:
        client_ip = extract_client_ip(
            request,
            trust_proxy=settings.trust_proxy,
            trusted_header=getattr(settings, "trusted_header", "auto"),
        )
        if not app.state.login_limiter.allow(client_ip, username):
            raise HTTPException(429, "Đã thử nhiều lần. Hãy đợi 15 phút rồi thử lại.")
        if not app.state.password_slots.acquire(blocking=False):
            raise HTTPException(429, "Máy chủ đang bận. Hãy thử lại sau.")
        return client_ip

    def start_session(db: Session, request: Request, user_id: str, version: str):
        now = datetime.now(timezone.utc)
        sid = secrets.token_urlsafe(32)
        db.execute(delete(AccessSession).where(AccessSession.expires_at <= now))
        prior = request.session.get("sid")
        if isinstance(prior, str):
            db.execute(delete(AccessSession).where(AccessSession.id == session_key(prior)))
        stale_ids = [
            row_id
            for (row_id,) in (
                db.query(AccessSession.id)
                .filter(AccessSession.user_id == user_id)
                .order_by(AccessSession.created_at.desc(), AccessSession.id.desc())
                .offset(MAX_SESSIONS_PER_USER - 1)
                .all()
            )
        ]
        if stale_ids:
            db.execute(delete(AccessSession).where(AccessSession.id.in_(stale_ids)))
        db.add(
            AccessSession(
                id=session_key(sid),
                user_id=user_id,
                password_version=version,
                expires_at=now + timedelta(days=SESSION_DAYS),
            )
        )
        db.commit()
        request.session.clear()
        request.session["sid"] = sid
        return {"authenticated": True}

    @router.post("/login")
    def login(payload: LoginInput, request: Request):
        if not settings.required:
            return {"authenticated": True}
        normalized_user = payload.username.strip().lower()
        client_ip = check_attempt(request, normalized_user)
        try:
            with Session(database.engine) as db:
                account = (
                    db.query(Account).filter_by(username=normalized_user).first()
                    if settings.accounts
                    else None
                )
                account_inactive = account is not None and not account.active
                if account is not None:
                    hashed = account.password_hash
                    target_id = account.id
                    account_exists = True
                elif not settings.accounts or normalized_user == "chuso":
                    hashed = settings.password_hash
                    target_id = OWNER_ID
                    account_exists = bool(hashed)
                else:
                    hashed = dummy_hash
                    target_id = ""
                    account_exists = False

                try:
                    valid = password_hasher.verify(payload.password, hashed or dummy_hash)
                except Exception:
                    valid = False

                if not valid or not account_exists or account_inactive:
                    raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu chưa đúng")

                app.state.login_limiter.refund_success(client_ip, normalized_user)
                return start_session(db, request, target_id, password_version(hashed))
        finally:
            app.state.password_slots.release()

    @router.post("/register")
    def register(payload: RegisterInput, request: Request):
        if not settings.accounts:
            raise HTTPException(404, "Chưa bật chế độ nhiều tài khoản")
        if not settings.can_register:
            raise HTTPException(
                403,
                "Đăng ký tài khoản mới đang khóa. Hãy liên hệ chủ ứng dụng để được cấp quyền.",
            )
        username = payload.username.lower()
        client_ip = check_attempt(request, username)
        try:
            if settings.invite_code and not hmac.compare_digest(
                payload.invite_code.strip().encode("utf-8"),
                settings.invite_code.encode("utf-8"),
            ):
                raise HTTPException(403, "Mã mời không hợp lệ")
            if username == "chuso":
                raise HTTPException(409, "Tên đăng nhập đã được sử dụng")
            hashed = password_hasher.hash(payload.password)
            with Session(database.engine) as db:
                account = Account(id=str(uuid4()), username=username, password_hash=hashed)
                db.add(account)
                from backend.finance_api import DEFAULT_CATEGORIES

                for name, color in DEFAULT_CATEGORIES:
                    db.add(Category(user_id=account.id, name=name, color=color))
                db.add(Preference(user_id=account.id, key="seeded", value="1"))
                try:
                    result = start_session(db, request, account.id, password_version(hashed))
                except IntegrityError:
                    db.rollback()
                    raise HTTPException(409, "Tên đăng nhập đã được sử dụng")
                app.state.login_limiter.refund_success(client_ip, username)
                return result
        finally:
            app.state.password_slots.release()

    @router.post("/change-password")
    def change_password(payload: ChangePasswordInput, request: Request):
        if not settings.required or not settings.accounts:
            raise HTTPException(
                400, "Chế độ hiện tại quản lý mật khẩu qua cấu hình môi trường máy chủ"
            )
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(401, "Vui lòng đăng nhập")
        client_ip = check_attempt(request, user["username"])
        try:
            with Session(database.engine) as db:
                account = db.get(Account, user["id"])
                if account is not None and not account.active:
                    raise HTTPException(401, "Tài khoản đã bị khóa")
                current_hash = account.password_hash if account else settings.password_hash
                try:
                    valid = password_hasher.verify(payload.current_password, current_hash)
                except Exception:
                    valid = False
                if not valid:
                    raise HTTPException(401, "Mật khẩu hiện tại chưa đúng")
                if payload.current_password == payload.new_password:
                    raise HTTPException(422, "Mật khẩu mới phải khác mật khẩu hiện tại")
                new_hash = password_hasher.hash(payload.new_password)
                if account:
                    account.password_hash = new_hash
                else:
                    account = Account(
                        id=user["id"],
                        username=user["username"],
                        password_hash=new_hash,
                        active=True,
                    )
                    db.add(account)
                db.execute(delete(AccessSession).where(AccessSession.user_id == user["id"]))
                app.state.login_limiter.refund_success(client_ip, user["username"])
                return start_session(db, request, user["id"], password_version(new_hash))
        finally:
            app.state.password_slots.release()

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
        user = getattr(request.state, "user", None)
        if user and database.engine is not None:
            with Session(database.engine) as db:
                db.execute(delete(AccessSession).where(AccessSession.user_id == user["id"]))
                db.commit()
        request.session.clear()
        return {"success": True}

    return router
