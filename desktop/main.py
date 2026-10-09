from __future__ import annotations

import logging
import socket
import threading
import time
import urllib.request

import uvicorn
import webview

from app.core.settings import app_data_dir
from app.main import app


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class DesktopApi:
    def choose_folder(self):
        windows = webview.windows
        if not windows:
            return None
        selected = windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return selected[0] if selected else None


def main() -> None:
    log_dir = app_data_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_dir / "desktop.log", encoding="utf-8", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.info("Desktop application starting")
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                            access_log=False, log_config=None)
    server = uvicorn.Server(config)
    worker = threading.Thread(target=server.run, name="local-api", daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{port}/"
    for _ in range(100):
        if not worker.is_alive():
            raise RuntimeError("本地服务启动失败，请检查 Python 依赖")
        try:
            with urllib.request.urlopen(url, timeout=0.3):
                break
        except Exception:
            time.sleep(0.1)
    else:
        server.should_exit = True
        raise RuntimeError("本地服务未能在预期时间内启动")

    webview.create_window("布店经营台", url, width=1440, height=920, min_size=(1120, 720),
                          background_color="#f5f7fb", js_api=DesktopApi())
    try:
        webview.start(gui="edgechromium", debug=False)
    except Exception:
        logging.exception("Desktop application failed")
        raise
    finally:
        server.should_exit = True
        worker.join(timeout=5)
        logging.info("Desktop application stopped")


if __name__ == "__main__":
    main()
