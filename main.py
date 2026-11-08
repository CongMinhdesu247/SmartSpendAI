import threading
import time
import webbrowser
import uvicorn

from backend.api_server import app, get_lan_ip
from backend.database import load_config
from backend.access import normalize_public_url

HOST = "0.0.0.0"
PORT = 8000


def open_browser_when_ready() -> None:
    """Tự động mở trình duyệt Web Dashboard trên máy tính sau khi FastAPI khởi động."""
    time.sleep(1.5)
    local_url = f"http://127.0.0.1:{PORT}"
    lan_url = f"http://{get_lan_ip()}:{PORT}"
    print("=" * 68)
    print("🚀 SMARTSPEND PRO ĐÃ KHỞI ĐỘNG THÀNH CÔNG!")
    print(f"💻 Truy cập trên Máy tính (Desktop): {local_url}")
    print(f"📱 Truy cập trên iPhone (Cùng Wi-Fi): {lan_url}")
    print("=" * 68)
    try:
        webbrowser.open(local_url)
    except Exception:
        pass


if __name__ == "__main__":
    cloud_url = normalize_public_url(load_config().get('cloud_url', ''))
    if cloud_url:
        webbrowser.open(cloud_url)
        raise SystemExit(0)
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")

