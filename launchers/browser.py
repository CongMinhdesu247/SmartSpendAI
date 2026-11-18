import os
import sys
import threading
import time
import webbrowser

import uvicorn

from backend.access import normalize_public_url
from backend.api_server import app, get_lan_ip
from backend.database import load_config

PORT = int(os.environ.get("SMARTSPEND_PORT", "8000"))


def resolve_bind_host() -> str:
    if os.environ.get("SMARTSPEND_HOST"):
        return os.environ["SMARTSPEND_HOST"]
    return "0.0.0.0" if load_config().get("allow_lan") else "127.0.0.1"


def open_browser_when_ready(bind_host: str) -> None:
    """Tự động mở trình duyệt Web Dashboard trên máy tính sau khi FastAPI khởi động."""
    time.sleep(1.5)
    local_url = f"http://127.0.0.1:{PORT}"
    print("=" * 68)
    print("SMARTSPEND PRO ĐÃ KHỞI ĐỘNG THÀNH CÔNG!")
    print(f"Truy cập trên Máy tính: {local_url}")
    if bind_host == "0.0.0.0":
        print(f"Truy cập trên iPhone (Cùng Wi-Fi): http://{get_lan_ip()}:{PORT}")
    else:
        print(
            "Chế độ bảo mật nội bộ: Chỉ mở trên máy này (127.0.0.1). Bật LAN trong Cài đặt nếu cần."
        )
    print("=" * 68)
    try:
        webbrowser.open(local_url)
    except Exception:
        pass


if __name__ == "__main__":
    force_local = "--local" in sys.argv
    cloud_url = "" if force_local else normalize_public_url(load_config().get("cloud_url", ""))
    if cloud_url:
        webbrowser.open(cloud_url)
        raise SystemExit(0)
    host = resolve_bind_host()
    threading.Thread(target=open_browser_when_ready, args=(host,), daemon=True).start()
    uvicorn.run(app, host=host, port=PORT, log_level="info")
