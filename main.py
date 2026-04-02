import multiprocessing
import threading
import time
import urllib.request

from app import app as app_instance
from app.config import redirect_stdio_if_frozen, setup_logging, FFMPEG_DIR
from app.state import state
from app.ffmpeg_manager import check_ffmpeg_async, cleanup_interrupted_downloads, monitor_heartbeat, open_browser_app, start_server


def wait_for_server(url, timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


if __name__ == '__main__':
    multiprocessing.freeze_support()

    redirect_stdio_if_frozen()
    setup_logging()

    check_ffmpeg_async(FFMPEG_DIR)

    cleanup_interrupted_downloads(state.download_dir)

    monitor_thread = threading.Thread(target=monitor_heartbeat, daemon=True)
    monitor_thread.start()

    server_thread = threading.Thread(target=start_server)
    server_thread.start()

    wait_for_server("http://127.0.0.1:4321")
    open_browser_app("http://127.0.0.1:4321")

    server_thread.join()
