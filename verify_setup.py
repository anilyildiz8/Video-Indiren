import sys
import shutil
import yt_dlp
import logging
import os

# Setup logging to console
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def check_ffmpeg():
    # 1. System PATH check
    if shutil.which("ffmpeg"):
        logging.info("INFO: FFmpeg found in system PATH.")
        return True
        
    # 2. Local folder check (same logic as main.py)
    local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg", "bin")
    if os.path.exists(local_ffmpeg):
        logging.info(f"INFO: Found local FFmpeg at {local_ffmpeg}. Temporarily adding to PATH for check...")
        os.environ["PATH"] += os.pathsep + local_ffmpeg
        if shutil.which("ffmpeg"):
             logging.info("INFO: Local FFmpeg looks good.")
             return True
             
    logging.error("ERROR: FFmpeg NOT found. It is required for merging audio/video.")
    return False

def check_ytdlp():
    try:
        logging.info(f"✅ yt-dlp imported successfully. Version: {yt_dlp.version.__version__}")
        return True
    except Exception as e:
        logging.error(f"❌ yt-dlp import failed: {e}")
        return False

def check_download_capability():
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw" # Me at the zoo (very short)
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'simulate': True, # Do not download
    }
    try:
        logging.info(f"Attempting to fetch metadata for: {test_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(test_url, download=False)
        logging.info("✅ Network and yt-dlp metadata extraction working.")
        return True
    except Exception as e:
        logging.error(f"❌ Metadata extraction failed: {e}")
        return False

if __name__ == "__main__":
    # Fix for Windows console encoding
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print("--- Video Downloader Environment Check ---")
    ffmpeg_ok = check_ffmpeg()
    ytdlp_ok = check_ytdlp()
    
    if ytdlp_ok:
        net_ok = check_download_capability()
    else:
        net_ok = False

    print("\n--- Summary ---")
    if ffmpeg_ok and ytdlp_ok and net_ok:
        print("INFO: Environment looks good! You can run 'python main.py'")
    else:
        print("WARNING: Issues detected. Please fix them before running the app.")
        if not ffmpeg_ok:
            print("  - FFmpeg is missing. Videos may not have audio or be low quality.")
            print("  - Download from: https://gyan.dev/ffmpeg/builds/ffmpeg-git-full.7z")
            print("  - Extract and add 'bin' folder to system PATH.")
