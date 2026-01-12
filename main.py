import os
import sys
import threading
import uvicorn
import webbrowser
import uuid
import subprocess
import anyio
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp
import logging
import time
import signal
import tkinter as tk
from tkinter import filedialog
import setup_ffmpeg
import multiprocessing
import json

# --- Logging Config ---
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- FIX: Redirect stdout/stderr for windowed EXE ---
if getattr(sys, 'frozen', False):
    # Redirect stdout and stderr to devnull to prevent crashes when console is missing
    f = open(os.devnull, 'w')
    sys.stdout = f
    sys.stderr = f
    # Also handle stdin
    sys.stdin = open(os.devnull, 'r')

import shutil

# --- 1. Path Management ---
def resource_path(relative_path):
    """ Get absolute path to resource """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --- 2. FastAPI Config ---
app = FastAPI()

# Mount static files - usage of resource_path is crucial here
static_dir = resource_path("static")
if not os.path.exists(static_dir):
    # Fallback for dev mode if referenced from script loc
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app.mount("/static", StaticFiles(directory=static_dir), name="static")

# --- 2. Global State ---
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".video_indiren_config.json")

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return data.get("download_dir")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
    return None

def save_config(download_dir):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"download_dir": download_dir}, f)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")

last_heartbeat_time = time.time() + 30.0 # 30s initial grace for slower PCs
server_should_exit = False
progress_state = {"percent": "0%", "speed": "0KB/s", "status": "idle"}
CURRENT_PROCESS_FILES = [] # Track files being downloaded in current session

# Preference Order: 1. Config File, 2. System Downloads, 3. Local Folder
saved_dir = load_config()
if saved_dir and os.path.exists(saved_dir):
    DOWNLOAD_DIR = saved_dir
else:
    DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
    if not os.path.exists(DOWNLOAD_DIR):
        DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

class DownloadRequest(BaseModel):
    url: str
    download_dir: str = None

def format_bytes(b):
    if b is None or b == 0: return "0.0B"
    # Using 1024 as yt-dlp uses binary prefixes for sizes
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(b) < 1024.0:
            return f"{b:3.1f}{unit}"
        b /= 1024.0
    return f"{b:.1f}TB"

def progress_hook(d):
    global progress_state, CURRENT_PROCESS_FILES
    if d['status'] == 'downloading':
        p = d.get('_percent_str', '0%')
        s = d.get('_speed_str', '0KB/s')
        filename = d.get('filename')
        
        dl = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        size_info = f"{format_bytes(dl)} / {format_bytes(total)}"
        
        if filename and filename not in CURRENT_PROCESS_FILES:
            CURRENT_PROCESS_FILES.append(filename)
        
        progress_state.update({
            "percent": p.strip(), 
            "speed": s.strip(), 
            "size_info": size_info,
            "status": "downloading"
        })
    elif d['status'] == 'finished':
        progress_state.update({
            "percent": "100%", 
            "speed": "0KB/s", 
            "status": "finished"
        })

@app.get("/api/progress")
async def get_progress():
    return progress_state

@app.post("/api/download")
async def download_video(request: DownloadRequest):
    global progress_state, CURRENT_PROCESS_FILES
    url = request.url
    download_id = str(uuid.uuid4())[:8]
    
    # Reset progress state
    progress_state = {"percent": "0%", "speed": "0KB/s", "status": "starting"}
    
    # Determine the download directory
    current_download_dir = DOWNLOAD_DIR
    if request.download_dir and os.path.exists(request.download_dir):
        current_download_dir = request.download_dir
    
    logger.info(f"Received download request for URL: {url} (ID: {download_id})")
    output_template = f"{current_download_dir}/{download_id}_%(title)s.%(ext)s"

    ydl_opts = {
        # Force MP4: best mp4 video + best m4a audio, or just best mp4
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'merge_output_format': 'mp4',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'restrictfilenames': True,
        'progress_hooks': [progress_hook],
    }

    def execute_download():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)

    try:
        logger.info(f"Starting download for ID: {download_id}")
        
        # Run blocking yt-dlp call in a separate thread to keep event loop free
        filename = await anyio.to_thread.run_sync(execute_download)

        # Post-download check for extension changes
        if not os.path.exists(filename):
            base = os.path.splitext(filename)[0]
            for ext in ['mp4', 'mkv', 'webm']:
                if os.path.exists(f"{base}.{ext}"):
                    filename = f"{base}.{ext}"
                    break
        
        full_path = os.path.abspath(filename)
        logger.info(f"Download successful for ID: {download_id}. Saved to: {full_path}")
            
        # Remove from cleanup list on success
        if filename in CURRENT_PROCESS_FILES:
            CURRENT_PROCESS_FILES.remove(filename)
        
        return {
            "status": "success",
            "message": "Video downloaded successfully",
            "filename": os.path.basename(filename),
            "full_path": full_path
        }

    except Exception as e:
        logger.error(f"Download error for ID {download_id}: {str(e)}", exc_info=True)
        print(f"Download error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/heartbeat")
async def heartbeat():
    global last_heartbeat_time
    last_heartbeat_time = time.time()
    return {"status": "ok"}

@app.get("/api/config")
async def get_config():
    return {"default_dir": DOWNLOAD_DIR}

@app.get("/api/select_folder")
async def select_folder():
    global DOWNLOAD_DIR
    root = tk.Tk()
    root.withdraw()
    # Ensure dialog is on top
    root.attributes('-topmost', True)
    folder_path = filedialog.askdirectory(initialdir=DOWNLOAD_DIR)
    root.destroy()
    if folder_path:
        DOWNLOAD_DIR = folder_path
        save_config(folder_path)
    return {"path": folder_path}

class OpenFolderRequest(BaseModel):
    file_path: str

@app.post("/api/open_folder")
async def open_folder(request: OpenFolderRequest):
    try:
        path = os.path.normpath(request.file_path)
        if os.path.exists(path):
            # Opens explorer and selects the file
            # This is the most robust way on Windows for frozen apps
            try:
                os.system(f'explorer /select,"{path}"')
                return {"status": "success"}
            except Exception as e:
                # Fallback to just opening the directory
                os.startfile(os.path.dirname(path))
                return {"status": "success"}
        else:
            return {"status": "error", "message": "File not found"}
    except Exception as e:
        logger.error(f"Failed to open folder: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/")
async def read_root():
    logger.info("Root page accessed")
    return FileResponse(os.path.join(static_dir, 'index.html'))


# --- 3. Desktop Application Launcher ---
def start_server():
    """Starts the Uvicorn server."""
    try:
        config = uvicorn.Config(app, host="127.0.0.1", port=4321, log_level="info")
        server = uvicorn.Server(config)
        server.run()
    except Exception as e:
        logger.error(f"Uvicorn failed to start: {e}")
        print(f"Server error: {e}")

def cleanup_interrupted_downloads():
    """Removes partial files if app closes mid-download."""
    global CURRENT_PROCESS_FILES
    logger.info(f"Cleaning up {len(CURRENT_PROCESS_FILES)} potential partial files...")
    for f in CURRENT_PROCESS_FILES:
        try:
            # Delete the main file if it exists (partial)
            if os.path.exists(f):
                os.remove(f)
            # Delete .part and .ytdl files
            for suffix in ['.part', '.ytdl']:
                pf = f + suffix
                if os.path.exists(pf):
                    os.remove(pf)
        except Exception as e:
            logger.error(f"Failed to cleanup {f}: {e}")

def monitor_heartbeat():
    """Monitors heartbeats and shuts down the process if none are received."""
    global last_heartbeat_time
    while True:
        time.sleep(2)
        if time.time() - last_heartbeat_time > 10:
            logger.info("No heartbeat received for 10 seconds. Shutting down...")
            cleanup_interrupted_downloads()
            # Use os._exit for a more forceful shutdown in the compiled EXE
            os._exit(0)
            break

def check_ffmpeg():
    # 1. Check if FFmpeg is already in PATH
    if shutil.which("ffmpeg"):
        logger.info("FFmpeg found in system PATH.")
        return

    # 2. Check for local 'ffmpeg/bin' folder (created by setup_ffmpeg.py)
    local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg", "bin")
    if os.path.exists(local_ffmpeg):
        logger.info(f"Found local FFmpeg at {local_ffmpeg}. Adding to PATH...")
        os.environ["PATH"] += os.pathsep + local_ffmpeg
        if shutil.which("ffmpeg"):
             logger.info("FFmpeg successfullly added to PATH.")
             return

    # 3. Auto-download
    logger.info("FFmpeg NOT found! Attempting automatic download...")
    print("FFmpeg not found. Downloading dependencies, please wait...")
    try:
        setup_ffmpeg.download_ffmpeg()
        # Verify again after download
        if os.path.exists(local_ffmpeg):
            os.environ["PATH"] += os.pathsep + local_ffmpeg
            if shutil.which("ffmpeg"):
                 logger.info("FFmpeg successfully installed and added to PATH.")
                 return
    except Exception as e:
        logger.error(f"Automatic FFmpeg download failed: {e}")

    logger.warning("FFmpeg NOT found! Video merging will fail or result in lower quality/no audio.")

def open_browser_app(url):
    """
    Forces opening in Edge App Mode by finding the executable directly.
    """
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
            subprocess.Popen([edge_exe, f"--app={url}"])
            return True
        except Exception as e:
            logger.error(f"Failed to launch Edge exe: {e}")
    
    # Try generic 'start' command for Edge App Mode fallback
    try:
        subprocess.Popen(['cmd', '/c', 'start', 'msedge', f'--app={url}'], shell=True)
        return True
    except:
        pass

    # Absolute last resort fallback: Default browser
    try:
        webbrowser.open(url)
        return True
    except Exception as e:
        logger.error(f"All browser launch attempts failed: {e}")
        return False

if __name__ == '__main__':
    multiprocessing.freeze_support()
    check_ffmpeg()
    
    # Launch browser after a slight delay to ensure server is starting
    try:
        url = "http://127.0.0.1:4321"
        logger.info(f"Opening browser at {url}")
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_heartbeat, daemon=True)
        monitor_thread.start()
        
        # Launch browser
        open_browser_app(url)
        
        print(f"App running at {url}. Monitoring heartbeat...")
        # Start server in main thread (blocking)
        start_server()
            
    except KeyboardInterrupt:
        print("\nStopping server...")
    except Exception as e:
        logger.error(f"Startup error: {e}")
        print(f"Error: {e}")
