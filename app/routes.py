import os
import time
import logging
import tkinter as tk
from tkinter import filedialog

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .state import state
from .config import load_config, save_config, FFMPEG_DIR
from .models import DownloadRequest, InfoRequest, QualityRequest, OpenFolderRequest
from .downloader import run_download, get_video_info
from .ffmpeg_manager import cleanup_interrupted_downloads, retry_ffmpeg_setup

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/progress")
async def get_progress():
    return state.progress_state


@router.get("/api/setup_status")
async def get_setup_status():
    return state.setup_state


@router.post("/api/retry_setup")
async def retry_setup():
    retry_status = retry_ffmpeg_setup(FFMPEG_DIR)
    return {
        "status": retry_status,
        "ffmpeg_available": state.setup_state.get("ffmpeg_available", False),
    }


@router.post("/api/cancel")
async def cancel_download():
    state.cancel_requested = True

    if state.active_ffmpeg_process and state.active_ffmpeg_process.poll() is None:
        try:
            state.active_ffmpeg_process.kill()
            state.active_ffmpeg_process.wait(timeout=5)
            logger.info("Killed active ffmpeg process.")
        except Exception:
            pass

    if os.name == "nt":
        try:
            import subprocess
            creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            subprocess.run(
                ['taskkill', '/F', '/IM', 'ffmpeg.exe', '/T'],
                capture_output=True,
                check=False,
                creationflags=creationflags,
            )
        except Exception:
            pass

    return {"status": "cancel_requested"}


@router.post("/api/download")
async def download_video(request: DownloadRequest):
    if not state.setup_state.get("ffmpeg_available", False):
        raise HTTPException(status_code=503, detail="Ilk kurulum tamamlanmadan indirme baslatilamaz.")

    download_dir = state.download_dir
    if request.download_dir and os.path.exists(request.download_dir):
        download_dir = request.download_dir

    try:
        result = await run_download(request.url, request, download_dir)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/heartbeat")
async def heartbeat():
    state.last_heartbeat_time = time.time()
    state.heartbeat_received = True
    return {"status": "ok"}


@router.post("/api/shutdown")
async def shutdown_app():
    state.server_should_exit = True
    return {"status": "shutting_down"}


@router.get("/api/config")
async def get_config():
    _, quality = load_config()
    return {"default_dir": state.download_dir, "quality": quality}


@router.post("/api/info")
async def get_video_info_route(request: InfoRequest):
    return await anyio.to_thread.run_sync(lambda: get_video_info(request.url))


@router.post("/api/set_quality")
async def set_quality(request: QualityRequest):
    save_config(quality=request.quality)
    return {"status": "ok"}


@router.get("/api/select_folder")
async def select_folder():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder_path = filedialog.askdirectory(initialdir=state.download_dir)
    root.destroy()
    if folder_path:
        state.download_dir = folder_path
        save_config(folder_path)
    return {"path": folder_path}


@router.post("/api/open_folder")
async def open_folder(request: OpenFolderRequest):
    try:
        path = os.path.normpath(request.file_path)
        if os.path.exists(path):
            target_dir = path if os.path.isdir(path) else os.path.dirname(path)
            os.startfile(target_dir)
            return {"status": "success"}
            
        # Fallback to parent directory (handles playlists with dummy file paths)
        target_dir = os.path.dirname(path)
        if target_dir and os.path.exists(target_dir):
            os.startfile(target_dir)
            return {"status": "success"}
            
        return {"status": "error", "message": "File not found"}
    except Exception as e:
        logger.error(f"Failed to open folder: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/")
async def read_root():
    from .utils import resource_path
    static_dir = resource_path("static")
    if not os.path.exists(static_dir):
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
    logger.info("Root page accessed")
    return FileResponse(os.path.join(static_dir, 'index.html'))
