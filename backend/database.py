import json
import os
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Generator, Optional
from urllib.parse import quote, unquote

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Đường dẫn thư mục gốc của dự án (hỗ trợ cả khi chạy code trực tiếp lẫn khi đóng gói PyInstaller .exe)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

if os.environ.get("SMARTSPEND_DATA_DIR"):
    BASE_DIR = Path(os.environ["SMARTSPEND_DATA_DIR"]).resolve()
    BASE_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = BASE_DIR / "config.json"
DEFAULT_SQLITE_URL = f"sqlite:///{(BASE_DIR / 'smartspend_local.db').as_posix()}"


class Base(DeclarativeBase):
    """Lớp cơ sở cho tất cả các model SQLAlchemy."""
    pass


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(connection, _record):
    import sqlite3
    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA foreign_keys=ON")


# Biến toàn cục quản lý kết nối Database hiện tại (cho phép hot-reload khi đổi cấu hình)
engine: Optional[Engine] = None
SessionLocal: Optional[sessionmaker] = None
current_db_mode: str = "sqlite"  # "postgresql" hoặc "sqlite"


def is_cloud_mode() -> bool:
    return os.environ.get("SMARTSPEND_CLOUD", "").lower() in ("1", "true")


def load_config() -> Dict[str, Any]:
    """Đọc cấu hình từ file config.json ở thư mục gốc. Tạo mặc định nếu chưa tồn tại."""
    default_cfg = {
        "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
        "database_url": os.environ.get("DATABASE_URL", ""),
        "cloud_url": os.environ.get("SMARTSPEND_PUBLIC_URL", "") or os.environ.get("RENDER_EXTERNAL_URL", ""),
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
                "gemini_api_key": data.get("gemini_api_key", "").strip(),
                "database_url": data.get("database_url", "").strip(),
                "cloud_url": data.get("cloud_url", "").strip(),
            }
    except Exception:
        return default_cfg


def save_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Lưu cấu hình gemini_api_key và database_url vào file config.json."""
    if is_cloud_mode():
        raise RuntimeError("Cấu hình cloud được quản lý qua biến môi trường")
    clean_cfg = {
        "gemini_api_key": str(cfg.get("gemini_api_key", "")).strip(),
        "database_url": str(cfg.get("database_url", "")).strip(),
        "cloud_url": str(cfg.get("cloud_url", "")).strip(),
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_cfg, f, indent=2, ensure_ascii=False)
    return clean_cfg


def normalize_database_url(raw_url: str) -> str:
    """
    Chuẩn hóa chuỗi kết nối Database:
    - Tự động chuyển 'postgres://' thành 'postgresql://' để tương thích với SQLAlchemy 1.4/2.0+.
    - Nếu để trống hoặc không hợp lệ, trả về chuỗi rỗng để kích hoạt cơ chế fallback SQLite.
    """
    if not raw_url:
        return ""
    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        # SQLAlchemy 2.1 defaults to psycopg3. This project installs psycopg2.
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    if url.startswith("postgresql+"):
        try:
            parsed = make_url(url)
            # Supabase passwords often contain '@'. A raw password must be URL-
            # encoded; repair only an invalid parsed hostname, not a valid URI.
            if parsed.host and "@" in parsed.host:
                scheme, rest = url.split("://", 1)
                credentials, destination = rest.rsplit("@", 1)
                username, password = credentials.split(":", 1)
                url = f"{scheme}://{quote(unquote(username), safe='')}:{quote(unquote(password), safe='')}@{destination}"
        except (ValueError, TypeError):
            pass
    return url


def init_db_connection(custom_url: Optional[str] = None) -> Dict[str, Any]:
    """
    Khởi tạo (hoặc khởi tạo lại) kết nối SQLAlchemy Engine & SessionLocal.
    - Nếu người dùng đã cấu hình PostgreSQL URI (Supabase): kết nối trực tiếp với pool_pre_ping=True.
    - Nếu chưa nhập hoặc kết nối lỗi: tự động fallback về SQLite cục bộ để ứng dụng không bị crash.
    """
    global engine, SessionLocal, current_db_mode

    cfg = load_config()
    raw_url = custom_url if custom_url is not None else cfg.get("database_url", "")
    normalized_url = normalize_database_url(raw_url)
    if is_cloud_mode() and not normalized_url.startswith(("postgresql://", "postgresql+")):
        raise RuntimeError("Cloud cần DATABASE_URL PostgreSQL; không dùng SQLite tạm")

    # Đóng engine cũ nếu đang tồn tại trước khi re-init
    if engine is not None:
        try:
            engine.dispose()
        except Exception:
            pass

    if normalized_url.startswith("postgresql://") or normalized_url.startswith("postgresql+"):
        try:
            test_engine = create_engine(
                normalized_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
                pool_recycle=300,
                connect_args={"connect_timeout": 10},
            )
            # Kiểm tra kết nối thực tế tới Supabase PostgreSQL
            with test_engine.connect() as conn:
                pass

            engine = test_engine
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            current_db_mode = "postgresql"

            # Import models và tạo bảng tự động trên Supabase nếu chưa có
            from backend import models, finance_models  # noqa: F401
            Base.metadata.create_all(bind=engine)

            if is_cloud_mode():
                with engine.begin() as conn:
                    for table in ("plans", "plan_items"):
                        conn.exec_driver_sql(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            return {
                "status": "connected",
                "mode": "postgresql",
                "message": "Đã kết nối thành công tới Supabase PostgreSQL trên đám mây!",
            }
        except Exception as exc:
            if is_cloud_mode():
                raise RuntimeError("Không kết nối được PostgreSQL. Kiểm tra DATABASE_URL trên hosting.") from None
            # Fallback an toàn về SQLite nếu chuỗi PostgreSQL bị sai mật khẩu hoặc mất mạng
            _init_sqlite_fallback()
            return {
                "status": "fallback",
                "mode": "sqlite",
                "message": "Không thể kết nối PostgreSQL. Đang tạm dùng SQLite cục bộ.",
            }
    else:
        _init_sqlite_fallback()
        return {
            "status": "local",
            "mode": "sqlite",
            "message": "Đang sử dụng cơ sở dữ liệu tạm SQLite cục bộ (chưa cấu hình Supabase PostgreSQL).",
        }


def _init_sqlite_fallback() -> None:
    """Hàm nội bộ khởi tạo SQLite fallback khi chưa có cấu hình Supabase."""
    global engine, SessionLocal, current_db_mode

    engine = create_engine(
        DEFAULT_SQLITE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    current_db_mode = "sqlite"

    from backend import models, finance_models  # noqa: F401
    # Keep a consistent SQLite snapshot before the first additive finance upgrade.
    from sqlalchemy import inspect
    local_path = Path(engine.url.database)
    backup_path = local_path.with_name(local_path.stem + '.before_finance_v1.db')
    existing_tables = inspect(engine).get_table_names()
    if 'plans' in existing_tables and 'spend_transactions' not in existing_tables and not backup_path.exists():
        import sqlite3
        with closing(sqlite3.connect(local_path)) as source, closing(sqlite3.connect(backup_path)) as target:
            source.backup(target)
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency cung cấp phiên làm việc (Session) của Database cho FastAPI."""
    global SessionLocal
    if SessionLocal is None:
        init_db_connection()

    db = SessionLocal()
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
    }

