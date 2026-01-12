import os
import sys
import zipfile
import shutil
import urllib.request
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DEST_DIR = os.path.join(os.getcwd(), "ffmpeg")
BIN_DIR = os.path.join(DEST_DIR, "bin")

def download_ffmpeg():
    if os.path.exists(BIN_DIR) and os.path.exists(os.path.join(BIN_DIR, "ffmpeg.exe")):
        logging.info("✅ FFmpeg is already installed in the 'ffmpeg' folder.")
        return

    logging.info("⬇️ Downloading FFmpeg... (this might take a minute)")
    zip_path = "ffmpeg.zip"
    
    try:
        # Download
        urllib.request.urlretrieve(FFMPEG_URL, zip_path)
        logging.info("📦 Extracting FFmpeg...")
        
        # Extract
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall("ffmpeg_temp")
        
        # Move bin folder to final location
        # The zip usually contains a root folder like 'ffmpeg-6.0-essentials_build'
        temp_root = "ffmpeg_temp"
        extracted_folders = os.listdir(temp_root)
        if not extracted_folders:
            raise Exception("Extraction failed, temp folder empty")
            
        source_dir = os.path.join(temp_root, extracted_folders[0])
        
        if os.path.exists(DEST_DIR):
            shutil.rmtree(DEST_DIR)
            
        shutil.move(source_dir, DEST_DIR)
        
        # Cleanup
        os.remove(zip_path)
        shutil.rmtree(temp_root)
        
        logging.info(f"✅ FFmpeg installed successfully to: {DEST_DIR}")
        logging.info("You don't need to change system PATH variables. The app will use this local version.")
        
    except Exception as e:
        logging.error(f"❌ Failed to download/install FFmpeg: {e}")
        # Cleanup partials
        if os.path.exists(zip_path): os.remove(zip_path)
        if os.path.exists("ffmpeg_temp"): shutil.rmtree("ffmpeg_temp")

if __name__ == "__main__":
    download_ffmpeg()
