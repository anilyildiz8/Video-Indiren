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

def download_ffmpeg(dest_dir=None):
    if dest_dir is None:
        dest_dir = os.path.join(os.getcwd(), "ffmpeg")
    
    bin_dir = os.path.join(dest_dir, "bin")
    
    if os.path.exists(bin_dir) and os.path.exists(os.path.join(bin_dir, "ffmpeg.exe")):
        logging.info(f"✅ FFmpeg already installed in: {bin_dir}")
        return

    logging.info("⬇️ Downloading FFmpeg... (this might take a minute)")
    zip_path = os.path.join(os.path.dirname(dest_dir), "ffmpeg.zip") if os.path.dirname(dest_dir) else "ffmpeg.zip"
    temp_extract = os.path.join(os.path.dirname(dest_dir), "ffmpeg_temp") if os.path.dirname(dest_dir) else "ffmpeg_temp"
    
    try:
        # Download
        urllib.request.urlretrieve(FFMPEG_URL, zip_path)
        logging.info("📦 Extracting FFmpeg...")
        
        # Extract
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extract)
        
        # Move bin folder to final location
        extracted_folders = os.listdir(temp_extract)
        if not extracted_folders:
            raise Exception("Extraction failed, temp folder empty")
            
        source_dir = os.path.join(temp_extract, extracted_folders[0])
        
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
            
        shutil.move(source_dir, dest_dir)
        
        # Cleanup
        if os.path.exists(zip_path): os.remove(zip_path)
        if os.path.exists(temp_extract): shutil.rmtree(temp_extract)
        
        logging.info(f"✅ FFmpeg installed successfully to: {dest_dir}")
        
    except Exception as e:
        logging.error(f"❌ Failed to download/install FFmpeg: {e}")
        # Cleanup partials
        if os.path.exists(zip_path): os.remove(zip_path)
        if os.path.exists(temp_extract): shutil.rmtree(temp_extract)

if __name__ == "__main__":
    download_ffmpeg()
