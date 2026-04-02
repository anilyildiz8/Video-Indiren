import os
import sys
import time
import shutil
import subprocess
import threading
import logging

from .state import state
from .config import FFMPEG_DIR
from .utils import resource_path

logger = logging.getLogger(__name__)


def _no_window_flags():
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _run_hidden(command):
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        creationflags=_no_window_flags(),
    )


def trim_video_ffmpeg(input_path, start_sec, end_sec):
    try:
        if state.cancel_requested:
            return input_path

        base, ext = os.path.splitext(input_path)
        trimmed_path = f"{base}_trimmed{ext}"

        cmd = [shutil.which('ffmpeg') or 'ffmpeg', '-y']

        cmd += ['-i', input_path]

        # Seek after input so the decoded trim starts exactly where the user
        # expects, then re-encode for broad thumbnail/preview compatibility.
        if start_sec and start_sec > 0:
            cmd += ['-ss', str(start_sec)]

        if end_sec is not None:
            duration = end_sec - (start_sec or 0)
            if duration > 0:
                cmd += ['-t', str(duration)]

        is_audio = ext.lower() in ['.mp3', '.m4a', '.wav', '.aac', '.ogg', '.flac', '.wma']

        cmd += ['-map', '0', '-map_metadata', '0']

        if is_audio:
            cmd += ['-c:v', 'copy']
            if ext.lower() == '.mp3':
                cmd += ['-c:a', 'libmp3lame', '-b:a', '192k']
            else:
                cmd += ['-c:a', 'aac', '-b:a', '192k']
        else:
            cmd += [
                '-c:v', 'libx264',
                '-preset', 'veryfast',
                '-crf', '18',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-movflags', '+faststart',
            ]

        cmd += [
            '-reset_timestamps', '1',
            '-avoid_negative_ts', 'make_zero',
            trimmed_path,
        ]

        logger.info(f"Trimming video: {' '.join(cmd)}")
        state.progress_state.update({"status": "trimming", "speed": "N/A", "percent": "100%", "size_info": "Video kesiliyor..."})

        state.active_ffmpeg_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=_no_window_flags()
        )

        _, stderr_data = state.active_ffmpeg_process.communicate()
        returncode = state.active_ffmpeg_process.returncode
        state.active_ffmpeg_process = None

        if returncode == 0 and os.path.exists(trimmed_path):
            try:
                os.remove(input_path)
                logger.info(f"Deleted original file: {input_path}")
            except Exception as e:
                logger.warning(f"Could not delete original: {e}")

            try:
                os.rename(trimmed_path, input_path)
                logger.info(f"Trim successful, replaced original file.")
                return input_path
            except Exception as e:
                logger.warning(f"Could not rename trimmed file: {e}")
                return trimmed_path
        else:
            stderr_text = stderr_data.decode(errors='ignore') if stderr_data else ''
            logger.error(f"FFmpeg trim failed (code {returncode}): {stderr_text}")
            if os.path.exists(trimmed_path):
                try:
                    os.remove(trimmed_path)
                except Exception:
                    pass
            return input_path
    except Exception as e:
        logger.error(f"Trim error: {e}")
        return input_path
    finally:
        state.active_ffmpeg_process = None


def cleanup_interrupted_downloads(download_dir):
    try:
        if os.path.exists(download_dir):
            logger.info(f"Aggressively cleaning up temporary files in {download_dir}...")

            if sys.platform == "win32":
                try:
                    _run_hidden(['taskkill', '/F', '/IM', 'ffmpeg.exe', '/T'])
                    time.sleep(1)
                except Exception:
                    pass

            for root, dirs, files in os.walk(download_dir):
                for file in files:
                    if any(ext in file.lower() for ext in ('.part', '.ytdl', '.temp', '.tmp', '.part-frag')):
                        file_path = os.path.join(root, file)
                        for attempt in range(5):
                            try:
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                                    if not os.path.exists(file_path):
                                        logger.info(f"Successfully deleted: {file}")
                                        break
                                    else:
                                        raise Exception("File still exists")
                            except Exception:
                                if attempt < 4:
                                    time.sleep(0.5)
    except Exception as e:
        logger.error(f"Aggressive cleanup failed: {e}")


def _check_ffmpeg_sync(ffmpeg_dir):
    import shutil
    if shutil.which("ffmpeg"):
        logger.info("FFmpeg found in system PATH.")
        return True

    bundled_ffmpeg_bin = resource_path(os.path.join("ffmpeg", "bin"))
    bundled_ffmpeg = os.path.join(bundled_ffmpeg_bin, "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if os.path.exists(bundled_ffmpeg):
        logger.info(f"Found bundled FFmpeg: {bundled_ffmpeg_bin}. Adding to PATH...")
        os.environ["PATH"] += os.pathsep + bundled_ffmpeg_bin
        if shutil.which("ffmpeg"):
            logger.info("FFmpeg successfully added to PATH from bundled resources.")
            return True

    appdata_ffmpeg_bin = os.path.join(ffmpeg_dir, "bin")
    if os.path.exists(appdata_ffmpeg_bin):
        logger.info(f"Found FFmpeg in AppData: {appdata_ffmpeg_bin}. Adding to PATH...")
        os.environ["PATH"] += os.pathsep + appdata_ffmpeg_bin
        if shutil.which("ffmpeg"):
            logger.info("FFmpeg successfully added to PATH from AppData.")
            return True

    local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg")
    if os.path.exists(local_ffmpeg):
        logger.info("Found legacy FFmpeg folder next to EXE. Cleaning up...")
        try:
            shutil.rmtree(local_ffmpeg)
        except Exception:
            pass

    return False


def _download_ffmpeg_with_progress(ffmpeg_dir):
    import shutil
    import setup_ffmpeg
    appdata_ffmpeg_bin = os.path.join(ffmpeg_dir, "bin")

    logger.info("FFmpeg NOT found! Attempting automatic download to AppData...")
    state.setup_state = {"status": "downloading", "progress": 0, "message": "FFmpeg indiriliyor...", "ffmpeg_available": False}

    try:
        def progress_callback(status, progress, message):
            state.setup_state = {
                "status": status,
                "progress": progress,
                "message": message,
                "ffmpeg_available": False,
            }

        setup_ffmpeg.download_ffmpeg(ffmpeg_dir, progress_callback=progress_callback)
        if os.path.exists(appdata_ffmpeg_bin):
            os.environ["PATH"] += os.pathsep + appdata_ffmpeg_bin
            if shutil.which("ffmpeg"):
                logger.info("FFmpeg successfully installed to AppData and added to PATH.")
                state.setup_state = {"status": "complete", "progress": 100, "message": "Kurulum tamamlandi", "ffmpeg_available": True}
                return True
    except Exception as e:
        logger.error(f"Automatic FFmpeg download failed: {e}")
        state.setup_state = {"status": "failed", "progress": 0, "message": f"FFmpeg yukleme hatasi: {str(e)}", "ffmpeg_available": False}

    logger.warning("FFmpeg NOT found! Video merging will fail or result in lower quality/no audio.")
    return False


def check_ffmpeg_async(ffmpeg_dir):
    if state.setup_in_progress:
        return

    if _check_ffmpeg_sync(ffmpeg_dir):
        state.setup_state = {"status": "complete", "progress": 100, "message": "FFmpeg hazir", "ffmpeg_available": True}
        state.setup_complete = True
        return

    def _run_download():
        state.setup_in_progress = True
        state.setup_complete = False
        try:
            _download_ffmpeg_with_progress(ffmpeg_dir)
        finally:
            state.setup_complete = True
            state.setup_in_progress = False

    t = threading.Thread(target=_run_download, daemon=True)
    t.start()


def retry_ffmpeg_setup(ffmpeg_dir):
    if state.setup_in_progress:
        return "in_progress"

    if _check_ffmpeg_sync(ffmpeg_dir):
        state.setup_state = {"status": "complete", "progress": 100, "message": "FFmpeg hazir", "ffmpeg_available": True}
        state.setup_complete = True
        return "complete"

    check_ffmpeg_async(ffmpeg_dir)
    return "started"


def monitor_heartbeat():
    while True:
        time.sleep(2)

        if state.server_should_exit:
            logger.info("Explicit shutdown requested. Shutting down...")
            state.cancel_requested = True
            time.sleep(1)
            cleanup_interrupted_downloads(state.download_dir)
            os._exit(0)
            break

        if not state.heartbeat_received:
            continue

        current_status = state.progress_state.get("status")
        if not state.setup_complete or current_status in {"starting", "downloading", "merging", "trimming"}:
            timeout = 180
        else:
            timeout = 60

        if time.time() - state.last_heartbeat_time > timeout:
            logger.info(f"No heartbeat received for {timeout} seconds. Shutting down...")
            state.cancel_requested = True
            time.sleep(3)
            cleanup_interrupted_downloads(state.download_dir)
            os._exit(0)
            break


def open_browser_app(url):
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")
    ]

    edge_exe = None
    for path in edge_paths:
        if os.path.exists(path):
            edge_exe = path
            break

    if edge_exe:
        try:
            logger.info(f"Found Edge at: {edge_exe}")
            subprocess.Popen([edge_exe, f"--app={url}"], creationflags=_no_window_flags())
            return True
        except Exception as e:
            logger.error(f"Failed to launch Edge exe: {e}")

    try:
        import webbrowser
        webbrowser.open(url)
        return True
    except Exception as e:
        logger.error(f"All browser launch attempts failed: {e}")
        return False


def start_server():
    import uvicorn
    try:
        from app import app
        config = uvicorn.Config(app, host="127.0.0.1", port=4321, log_level="info")
        server = uvicorn.Server(config)
        server.run()
    except Exception as e:
        logger.error(f"Uvicorn failed to start: {e}")
