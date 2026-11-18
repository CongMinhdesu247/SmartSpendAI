import json
import logging
import os
import sys
import threading
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Generator, Optional
from urllib.parse import quote, unquote

from fastapi import HTTPException, Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.tenancy import OWNER_ID, LedgerSession


def _resolve_base_dir() -> Path:
    if os.environ.get("SMARTSPEND_DATA_DIR"):
        custom = Path(os.environ["SMARTSPEND_DATA_DIR"]).resolve()
        custom.mkdir(parents=True, exist_ok=True)
        return custom

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        # Preserve portable mode if data already lives beside the EXE and is writable;
        # otherwise use %LOCALAPPDATA%\SmartSpendPro so Program Files installs never fail.
        has_portable_files = (exe_dir / "config.json").exists() or (
            exe_dir / "smartspend_local.db"
        ).exists()
        if has_portable_files and os.access(exe_dir, os.W_OK):
            return exe_dir
        appdata = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "SmartSpendPro"
        appdata.mkdir(parents=True, exist_ok=True)
        return appdata

    return Path(__file__).resolve().parent.parent


BASE_DIR = _resolve_base_dir()
CONFIG_FILE = BASE_DIR / "config.json"
DEFAULT_SQLITE_URL = f"sqlite:///{(BASE_DIR / 'smartspend_local.db').as_posix()}"


class Base(DeclarativeBase):
    """Lớp cơ sở cho tất cả các model SQLAlchemy."""

    pass


def load_all_models() -> None:
    """Đăng ký tường minh toàn bộ các module ORM model vào Base.metadata."""
    from backend import auth_models, finance_models, models  # noqa: F401



@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, _record):
    import sqlite3

    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")


# Biến toàn cục quản lý kết nối Database hiện tại (cho phép hot-reload khi đổi cấu hình)
engine: Optional[Engine] = None
SessionLocal: Optional[sessionmaker] = None
current_db_mode: str = "sqlite"  # "postgresql" hoặc "sqlite"
connection_lock = threading.RLock()
logger = logging.getLogger(__name__)


class DatabaseConnectionError(RuntimeError):
    pass


def is_cloud_mode() -> bool:
    return os.environ.get("SMARTSPEND_CLOUD", "").lower() in ("1", "true")


def load_config() -> Dict[str, Any]:
    """Đọc cấu hình từ file config.json ở thư mục dữ liệu. Tạo mặc định nếu chưa tồn tại."""
    default_cfg = {
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "database_url": os.environ.get("DATABASE_URL", ""),
        "cloud_url": os.environ.get("SMARTSPEND_PUBLIC_URL", "")
        or os.environ.get("RENDER_EXTERNAL_URL", ""),
        "allow_lan": os.environ.get("SMARTSPEND_ALLOW_LAN", "").lower() in ("1", "true"),
    }
    if is_cloud_mode():
        return default_cfg  # Hosted secrets are environment-only; never config.json.
    if not CONFIG_FILE.exists():
        save_config(default_cfg)
        return default_cfg

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "gemini_api_key": str(data.get("gemini_api_key", "")).strip(),
                "database_url": str(data.get("database_url", "")).strip(),
                "cloud_url": str(data.get("cloud_url", "")).strip(),
                "allow_lan": bool(data.get("allow_lan", False)),
            }
    except Exception:
        return default_cfg


def save_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Lưu cấu hình vào file config.json an toàn (atomic replace)."""
    if is_cloud_mode():
        raise RuntimeError("Cấu hình cloud được quản lý qua biến môi trường")
    clean_cfg = {
        "gemini_api_key": str(cfg.get("gemini_api_key", "")).strip(),
        "database_url": str(cfg.get("database_url", "")).strip(),
        "cloud_url": str(cfg.get("cloud_url", "")).strip(),
        "allow_lan": bool(cfg.get("allow_lan", False)),
    }
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_FILE.with_suffix(".json.tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(clean_cfg, f, indent=2, ensure_ascii=False)
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(CONFIG_FILE)
    return clean_cfg


def normalize_database_url(raw_url: str) -> str:
    """
    Chuẩn hóa chuỗi kết nối Database:
    - Tự động chuyển 'postgres://' thành 'postgresql://' để tương thích với SQLAlchemy 2.0+.
    - Nếu để trống, trả về chuỗi rỗng để dùng SQLite cục bộ.
    """
    if not raw_url:
        return ""
    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        # SQLAlchemy 2.1 defaults to psycopg3. This project installs psycopg2.
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    if url.startswith("postgresql+"):
        try:
            parsed = make_url(url)
            if parsed.host and "@" in parsed.host:
                scheme, rest = url.split("://", 1)
                credentials, destination = rest.rsplit("@", 1)
                username, password = credentials.split(":", 1)
                url = (
                    f"{scheme}://{quote(unquote(username), safe='')}:"
                    f"{quote(unquote(password), safe='')}@{destination}"
                )
        except (ValueError, TypeError):
            pass
    return url


def init_db_connection(custom_url: Optional[str] = None, config_to_save=None) -> Dict[str, Any]:
    """
    Khởi tạo (hoặc khởi tạo lại) kết nối SQLAlchemy Engine & SessionLocal.
    """
    global engine, SessionLocal, current_db_mode
    with connection_lock:
        raw_url = custom_url if custom_url is not None else load_config().get("database_url", "")
        normalized_url = normalize_database_url(raw_url)
        postgres = normalized_url.startswith(("postgresql://", "postgresql+"))
        if (normalized_url and not postgres) or (is_cloud_mode() and not postgres):
            raise DatabaseConnectionError(
                "Địa chỉ database phải là PostgreSQL. Để trống để chọn SQLite trên máy tính."
            )
        candidate = None
        try:
            if postgres:
                candidate = create_engine(
                    normalized_url,
                    pool_pre_ping=True,
                    pool_size=5,
                    max_overflow=10,
                    pool_recycle=300,
                    connect_args={"connect_timeout": 10},
                )
                from backend.account_migration import require_ready

                require_ready(candidate)
            else:
                candidate = _create_sqlite_engine()
            from backend.finance_api import initialize_finance

            initialize_finance(candidate)
            if config_to_save is not None:
                save_config(config_to_save)
        except Exception as exc:
            if candidate is not None:
                candidate.dispose()
            logger.error("Database connection/setup failed (%s)", type(exc).__name__)
            raise DatabaseConnectionError(
                "Chưa kết nối được database hoặc chưa nâng cấp schema/quyền. "
                "Kiểm tra kết nối và hướng dẫn python -m scripts.cloud.migrate_ledgers. "
                "Cấu hình và nguồn dữ liệu hiện tại được giữ nguyên."
            ) from None
        previous = engine
        engine = candidate
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        current_db_mode = "postgresql" if postgres else "sqlite"
        if previous is not None and previous is not candidate:
            previous.dispose()
        return {
            "status": "connected" if postgres else "local",
            "mode": current_db_mode,
            "message": (
                "Đã kết nối PostgreSQL." if postgres else "Đang lưu dữ liệu SQLite trên máy tính."
            ),
        }


def _init_sqlite_fallback() -> None:
    """Hàm nội bộ khởi tạo SQLite fallback khi chưa có cấu hình PostgreSQL."""
    global engine, SessionLocal, current_db_mode

    engine = _create_sqlite_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    current_db_mode = "sqlite"


def _create_sqlite_engine() -> Engine:
    local_engine = create_engine(
        DEFAULT_SQLITE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    load_all_models()
    from sqlalchemy import inspect

    local_path = Path(local_engine.url.database)
    backup_path = local_path.with_name(local_path.stem + ".before_finance_v1.db")
    existing_tables = inspect(local_engine).get_table_names()
    if (
        "plans" in existing_tables
        and "spend_transactions" not in existing_tables
        and not backup_path.exists()
    ):
        import sqlite3

        with (
            closing(sqlite3.connect(local_path)) as source,
            closing(sqlite3.connect(backup_path)) as target,
        ):
            source.backup(target)
    from backend.sqlite_upgrade import upgrade_local

    try:
        upgrade_local(local_engine)
        Base.metadata.create_all(bind=local_engine)
        return local_engine
    except Exception:
        local_engine.dispose()
        raise


def get_db(request: Request) -> Generator[Session, None, None]:
    """Dependency cung cấp phiên làm việc (Session) của Database cho FastAPI."""
    global SessionLocal
    if SessionLocal is None:
        init_db_connection()

    user = getattr(request.state, "user", None)
    if is_cloud_mode() and not user:
        raise HTTPException(401, "Vui lòng đăng nhập")
    db = LedgerSession(engine, user_id=user["id"] if user else OWNER_ID)
    try:
        yield db
    finally:
        db.close()


def get_db_status() -> Dict[str, Any]:
    """Trả về trạng thái kết nối Database hiện tại để hiển thị trên giao diện."""
    cfg = load_config()
    raw_url = cfg.get("database_url", "")
    masked_url = ""
    if raw_url:
        try:
            parsed = make_url(normalize_database_url(raw_url))
            masked_url = parsed.set(query={}).render_as_string(hide_password=True)
        except Exception:
            masked_url = "Đã cấu hình"

    return {
        "mode": current_db_mode,
        "is_cloud_postgres": current_db_mode == "postgresql",
        "configured_url_masked": masked_url,
        "data_dir": str(BASE_DIR),
    }
