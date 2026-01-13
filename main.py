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
import re

# --- AppData Management ---
def get_app_data_dir():
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~\\AppData\\Roaming'))
    else:
        base = os.path.expanduser('~/.config')
    
    app_dir = os.path.join(base, 'VideoIndiren')
    if not os.path.exists(app_dir):
        os.makedirs(app_dir)
    return app_dir

APP_DATA_DIR = get_app_data_dir()
LOG_FILE = os.path.join(APP_DATA_DIR, 'app.log')
CONFIG_FILE = os.path.join(APP_DATA_DIR, 'config.json')
FFMPEG_DIR = os.path.join(APP_DATA_DIR, 'ffmpeg')

# --- Logging Config ---
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return data.get("download_dir"), data.get("quality", "best")
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
    return None, "best"

def save_config(download_dir=None, quality=None):
    try:
        current_dir, current_quality = load_config()
        new_dir = download_dir if download_dir is not None else current_dir
        new_quality = quality if quality is not None else current_quality
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"download_dir": new_dir, "quality": new_quality}, f)
    except Exception as e:
        logger.error(f"Failed to save config: {e}")

last_heartbeat_time = time.time() + 30.0 # 30s initial grace for slower PCs
server_should_exit = False
progress_state = {"percent": "0%", "speed": "0KB/s", "status": "idle", "playlist_info": ""}
CURRENT_PROCESS_FILES = [] # Track files being downloaded in current session
cancel_requested = False # Global flag for cancellation

# Preference Order: 1. Config File, 2. System Downloads, 3. Local Folder
saved_dir, saved_quality = load_config()
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
    quality: str = "best"
    audio_only: bool = False
    download_playlist: bool = False

def format_bytes(b):
    if b is None or b == 0: return "0.0B"
    # Using 1024 as yt-dlp uses binary prefixes for sizes
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(b) < 1024.0:
            return f"{b:3.1f}{unit}"
        b /= 1024.0
    return f"{b:.1f}TB"

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def postprocessor_hook(d):
    global progress_state
    if d['status'] == 'started':
        progress_state.update({"status": "merging", "speed": "N/A"})
    elif d['status'] == 'finished':
        progress_state.update({"status": "finished", "percent": "100%"})

def progress_hook(d):
    global progress_state, CURRENT_PROCESS_FILES, cancel_requested
    
    if cancel_requested:
        raise ValueError("DOWNLOAD_CANCELLED")

    if d['status'] == 'downloading':
        p = strip_ansi(d.get('_percent_str', '0%')).strip()
        s = strip_ansi(d.get('_speed_str', '0KB/s')).strip()
        filename = d.get('filename')
        
        dl = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        size_info = f"{format_bytes(dl)} / {format_bytes(total)}"
        
        # Playlist info - try both top-level and info_dict (some extractors use different levels)
        info_dict = d.get('info_dict', {})
        playlist_index = d.get('playlist_index') or info_dict.get('playlist_index')
        n_entries = d.get('n_entries') or info_dict.get('n_entries')
        
        playlist_info = ""
        if playlist_index is not None and n_entries is not None:
            playlist_info = f"{playlist_index} / {n_entries}"

        if filename and filename not in CURRENT_PROCESS_FILES:
            CURRENT_PROCESS_FILES.append(filename)
        
        progress_state.update({
            "percent": p, 
            "speed": s, 
            "size_info": size_info,
            "playlist_info": playlist_info,
            "status": "downloading"
        })
    elif d['status'] == 'finished':
        filename = d.get('filename')
        # On success, immediately remove from cleanup list so it's persisted even on late cancel
        if filename and filename in CURRENT_PROCESS_FILES:
            CURRENT_PROCESS_FILES.remove(filename)

        progress_state.update({
            "percent": "100%", 
            "speed": "0KB/s", 
            "status": "finished"
        })

@app.get("/api/progress")
async def get_progress():
    return progress_state

@app.post("/api/cancel")
async def cancel_download():
    global cancel_requested
    cancel_requested = True
    return {"status": "cancel_requested"}

@app.post("/api/download")
async def download_video(request: DownloadRequest):
    global progress_state, CURRENT_PROCESS_FILES, cancel_requested
    url = request.url
    download_id = str(uuid.uuid4())[:8]
    
    # Reset state for new download
    cancel_requested = False
    progress_state = {"percent": "0%", "speed": "0KB/s", "status": "starting", "playlist_info": ""}
    
    # Determine the download directory
    current_download_dir = DOWNLOAD_DIR
    if request.download_dir and os.path.exists(request.download_dir):
        current_download_dir = request.download_dir
    
    logger.info(f"Received download request for URL: {url} (ID: {download_id}, Quality: {request.quality}, Audio: {request.audio_only}, Playlist: {request.download_playlist})")
    
    # Template: Include playlist index if it's a playlist to avoid name collisions
    if request.download_playlist:
        output_template = f"{current_download_dir}/%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s"
    else:
        # Use video ID in bracket to be unique but stable for duplicate detection
        output_template = f"{current_download_dir}/%(title)s [%(id)s].%(ext)s"

    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'nocolor': True,
        'restrictfilenames': False,
        'progress_hooks': [progress_hook],
        'postprocessor_hooks': [postprocessor_hook],
        'noplaylist': not request.download_playlist,
        'nooverwrites': True, # Skip if file exists
        'concurrent_fragment_downloads': 10, # Keep fast fragments
        'nocheckcertificate': True,
        'geo_bypass': True,
        'prefer_ffmpeg': True,
        'windows_filenames': True,
        # Strict format sorting to prefer MP4 and M4A
        'format_sort': ['res', 'ext:mp4:m4a'],
        # Proven fast merge strategy
        'postprocessor_args': {
            'merger': ['-c', 'copy']
        }
    }

    if request.audio_only:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        # Dynamic format selection based on quality
        if request.quality == "4k":
            fmt = 'bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[height<=2160]/best'
        elif request.quality == "1080p":
            fmt = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best'
        elif request.quality == "720p":
            fmt = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best'
        elif request.quality == "480p":
            fmt = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]/best'
        else: # best
            fmt = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
        
        ydl_opts['format'] = fmt
        ydl_opts['merge_output_format'] = 'mp4'

    def execute_download():
        target_template = output_template
        
        # Dynamic numbering for playlists
        if request.download_playlist:
            try:
                # Fast pre-scan to get entry count
                with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True, 'nocheckcertificate': True}) as ydl_meta:
                    meta = ydl_meta.extract_info(url, download=False)
                    if meta and 'entries' in meta:
                        count = len(list(meta['entries']))
                        padding = "03d" if count >= 100 else ("02d" if count >= 10 else "s")
                        target_template = f"{current_download_dir}/%(playlist_title)s/%(playlist_index){padding} - %(title)s.%(ext)s"
                        logger.info(f"Playlist detected with {count} entries. Using padding: {padding}")
            except Exception as e:
                logger.warning(f"Failed to pre-scan playlist for numbering: {e}")

        final_opts = ydl_opts.copy()
        final_opts['outtmpl'] = target_template

        with yt_dlp.YoutubeDL(final_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # Use prepare_filename on the top-level info
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
        if str(e) == "DOWNLOAD_CANCELLED":
            logger.info(f"Download {download_id} was cancelled by user.")
            progress_state["status"] = "cancelled"
            cleanup_interrupted_downloads()
            return {"status": "cancelled", "message": "İndirme iptal edildi"}
        
        logger.error(f"Download error for ID {download_id}: {str(e)}", exc_info=True)
        print(f"Download error: {str(e)}")
        progress_state["status"] = "error"
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/heartbeat")
async def heartbeat():
    global last_heartbeat_time
    last_heartbeat_time = time.time()
    return {"status": "ok"}

@app.get("/api/config")
async def get_config():
    _, quality = load_config()
    return {"default_dir": DOWNLOAD_DIR, "quality": quality}

class QualityRequest(BaseModel):
    quality: str

@app.post("/api/set_quality")
async def set_quality(request: QualityRequest):
    save_config(quality=request.quality)
    return {"status": "ok"}

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

def cleanup_interrupted_downloads():
    """Delete leftover temporary files aggressively."""
    try:
        # Search in the main download directory and its subfolders
        if os.path.exists(DOWNLOAD_DIR):
            logger.info(f"Aggressively cleaning up temporary files in {DOWNLOAD_DIR}...")
            
            # Forcefully stop any merging processes to release file locks on Windows
            if sys.platform == "win32":
                try:
                    import subprocess
                    subprocess.run(['taskkill', '/F', '/IM', 'ffmpeg.exe', '/T'], capture_output=True, check=False)
                    time.sleep(1) # Wait for OS to settle
                except:
                    pass

            for root, dirs, files in os.walk(DOWNLOAD_DIR):
                for file in files:
                    if any(ext in file.lower() for ext in ('.part', '.ytdl', '.temp', '.tmp', '.part-frag')):
                        file_path = os.path.join(root, file)
                        # Deletion loop to ensure lock release
                        for attempt in range(5):
                            try:
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                                    if not os.path.exists(file_path):
                                        logger.info(f"Successfully deleted: {file}")
                                        break
                                    else:
                                        raise Exception("File still exists")
                            except:
                                if attempt < 4:
                                    time.sleep(0.5)
    except Exception as e:
        logger.error(f"Aggressive cleanup failed: {e}")

def monitor_heartbeat():
    """Monitors heartbeats and shuts down the process if none are received."""
    global last_heartbeat_time
    while True:
        time.sleep(2)
        if time.time() - last_heartbeat_time > 10:
            logger.info("No heartbeat received for 10 seconds. Shutting down...")
            global cancel_requested
            cancel_requested = True
            time.sleep(3) 
            cleanup_interrupted_downloads()
            os._exit(0)
            break

def check_ffmpeg():
    # 1. Check if FFmpeg is already in PATH (System installed)
    if shutil.which("ffmpeg"):
        logger.info("FFmpeg found in system PATH.")
        return

    # 2. Check for AppData 'ffmpeg/bin' folder
    appdata_ffmpeg_bin = os.path.join(FFMPEG_DIR, "bin")
    if os.path.exists(appdata_ffmpeg_bin):
        logger.info(f"Found FFmpeg in AppData: {appdata_ffmpeg_bin}. Adding to PATH...")
        os.environ["PATH"] += os.pathsep + appdata_ffmpeg_bin
        if shutil.which("ffmpeg"):
             logger.info("FFmpeg successfully added to PATH from AppData.")
             return

    # 3. Legacy check & cleanup: If found next to EXE, move or delete it
    local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg")
    if os.path.exists(local_ffmpeg):
        logger.info("Found legacy FFmpeg folder next to EXE. Cleaning up...")
        try:
            shutil.rmtree(local_ffmpeg)
        except:
            pass

    # 4. Auto-download to AppData
    logger.info("FFmpeg NOT found! Attempting automatic download to AppData...")
    print("FFmpeg not found. Downloading dependencies to AppData, please wait...")
    try:
        setup_ffmpeg.download_ffmpeg(FFMPEG_DIR)
        # Verify again after download
        if os.path.exists(appdata_ffmpeg_bin):
            os.environ["PATH"] += os.pathsep + appdata_ffmpeg_bin
            if shutil.which("ffmpeg"):
                 logger.info("FFmpeg successfully installed to AppData and added to PATH.")
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
    
    # Startup Sweep: Clean any leftovers from previous crashed sessions
    cleanup_interrupted_downloads()
    
    # Launch browser after a slight delay to ensure server is starting
    try:
        url = "http://127.0.0.1:4321"
        logger.info(f"Opening browser at {url}")
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_heartbeat, daemon=True)
        monitor_thread.start()
        
        # Launch browser
        open_browser_app(url)
        
        # Start server in main thread (blocking)
        start_server()
            
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Startup error: {e}")
        print(f"Error: {e}")
