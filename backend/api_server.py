"""FastAPI application entrypoint wiring modular routers and guarded static frontend."""

from contextlib import asynccontextmanager
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend import database
from backend.access import install_access
from backend.ai_service import (  # noqa: F401
    analyze_monthly_spending,
    generate_smart_plan,
    suggest_replacement,
)
from backend.finance_api import initialize_finance
from backend.routers.finance import router as finance_router
from backend.routers.plans import recalculate_plan_totals, router as plans_router  # noqa: F401
from backend.routers.system import (  # noqa: F401
    get_config,
    get_lan_ip,
    get_network_info,
    health,
    network_qr,
    router as system_router,
    update_config,
)

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    FRONTEND_DIR = Path(sys._MEIPASS) / "frontend"
else:
    FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

_BLOCKED_STATIC_FILES = {"tailwind.input.css"}


class _GuardedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        normalized = path.lstrip("/").replace("\\", "/")
        if normalized in _BLOCKED_STATIC_FILES or normalized.startswith("."):
            raise StarletteHTTPException(status_code=404)
        return await super().get_response(path, scope)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo kết nối Database khi máy chủ khởi động."""
    app.state.access.validate()
    database.init_db_connection()
    initialize_finance(database.engine)
    yield


app = FastAPI(
    title="SmartSpend Pro API",
    description="API Quản lý tài chính, Thực đơn đi chợ & Kế hoạch thông minh với AI.",
    version="2.1.0",
    lifespan=lifespan,
    docs_url=None if database.is_cloud_mode() else "/docs",
    redoc_url=None if database.is_cloud_mode() else "/redoc",
    openapi_url=None if database.is_cloud_mode() else "/openapi.json",
)

install_access(app)
app.include_router(system_router)
app.include_router(plans_router)
app.include_router(finance_router)


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
        "/",
        _GuardedStaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend_root",
    )
