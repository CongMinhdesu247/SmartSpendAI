import socket
import threading
import time
import webbrowser

import uvicorn

from backend.api_server import app, get_lan_ip
from backend.database import load_config, BASE_DIR
from backend.access import normalize_public_url

HOST = "0.0.0.0"
PORT = 8000
LOCAL_URL = f"http://127.0.0.1:{PORT}"


def run_fastapi_server() -> None:
    """Chạy FastAPI server trên 0.0.0.0:8000 để cả Desktop và iPhone cùng mạng Wi-Fi đều truy cập được."""
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def wait_for_server_ready(timeout: float = 12.0) -> bool:
    """Đợi cho tới khi cổng 8000 sẵn sàng nhận kết nối."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main() -> None:
    cloud_url = normalize_public_url(load_config().get('cloud_url', ''))
    if cloud_url:
        try:
            import webview
            webview.create_window('SmartSpend Pro', cloud_url, width=1360, height=860, min_size=(960, 640))
            webview.start(private_mode=False, storage_path=str(BASE_DIR / 'webview_profile'))
        except ImportError:
            webbrowser.open(cloud_url)
        return
    # 1. Khởi chạy uvicorn server trong daemon thread
    server_thread = threading.Thread(target=run_fastapi_server, daemon=True)
    server_thread.start()

    # 2. Đợi server sẵn sàng
    wait_for_server_ready()

    lan_ip = get_lan_ip()
    print("=" * 70)
    print("💎 SMARTSPEND PRO - AI CLOUD FINANCE & PLANNER")
    print(f"🖥️  Desktop App URL : {LOCAL_URL}")
    print(f"📱 iPhone Wi-Fi URL: http://{lan_ip}:{PORT}")
    print("=" * 70)

    # 3. Mở cửa sổ Desktop Native bằng pywebview (fallback sang trình duyệt nếu máy chưa cài pywebview)
    try:
        import webview

        webview.create_window(
            "SmartSpend Pro - AI Cloud Finance & Planner",
            LOCAL_URL,
            width=1360,
            height=860,
            min_size=(960, 640),
        )
        webview.start()
    except ImportError:
        print("[!] Thư viện 'pywebview' chưa được cài đặt. Đang mở trên trình duyệt mặc định...")
        webbrowser.open(LOCAL_URL)
        try:
            while server_thread.is_alive():
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\nĐã dừng SmartSpend Pro.")


if __name__ == "__main__":
    main()

