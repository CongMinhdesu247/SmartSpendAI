"""Desktop entry point with HTTP readiness checks and persistent startup logs."""
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import threading
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

HOST = "0.0.0.0"
PORT = 8000
LOCAL_URL = f"http://127.0.0.1:{PORT}"
logger = logging.getLogger(__name__)


def configure_logging():
    folder = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "SmartSpendPro" / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "desktop.log"
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    return path


def wait_for_server_ready(timeout=15.0, server=None, thread=None):
    deadline = time.monotonic() + timeout
    opener = build_opener(ProxyHandler({}))
    while time.monotonic() < deadline:
        if thread is not None and not thread.is_alive():
            return False
        if server is None or server.started:
            try:
                with opener.open(LOCAL_URL + "/healthz", timeout=0.5) as response:
                    if response.status == 200 and response.headers.get("X-SmartSpend-App") == "1":
                        return True
            except (OSError, URLError):
                pass
        time.sleep(0.2)
    return False


def show_startup_error(message):
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "SmartSpend Pro — Lỗi khởi động", 0x10)
    else:
        print(message)


def open_window(url):
    try:
        import webview
        from backend.database import BASE_DIR
        webview.create_window("SmartSpend Pro", url, width=1360, height=860, min_size=(960, 640))
        webview.start(private_mode=False, storage_path=str(BASE_DIR / "webview_profile"))
        return True
    except Exception as exc:
        logger.warning("Desktop window unavailable (%s); opening browser", type(exc).__name__)
        webbrowser.open(url)
        return False


def main(check_startup=False):
    log_path = configure_logging()
    server = None
    thread = None
    try:
        from backend.database import load_config
        from backend.access import normalize_public_url
        cloud_url = normalize_public_url(load_config().get("cloud_url", ""))
        if cloud_url:
            if check_startup:
                logger.info("Cloud launcher configuration loaded")
                return 0
            open_window(cloud_url)
            return 0
        import uvicorn
        from backend.api_server import app
        server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning", log_config=None))

        def run_server():
            try:
                server.run()
            except BaseException as exc:
                logger.error("Local server stopped (%s)", type(exc).__name__)

        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        if not wait_for_server_ready(server=server, thread=thread):
            raise RuntimeError("Server did not become ready")
        if check_startup:
            logger.info("Local startup check passed")
            return 0
        if not open_window(LOCAL_URL):
            while thread.is_alive():
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logger.error("Desktop startup failed (%s)", type(exc).__name__)
        if check_startup:
            return 1
        show_startup_error(
            "Chưa khởi động được SmartSpend. Kiểm tra cổng 8000 có bị chiếm, "
            "kết nối database và bước nâng cấp schema.\n\nNhật ký: " + str(log_path))
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(check_startup="--check-startup" in sys.argv))
