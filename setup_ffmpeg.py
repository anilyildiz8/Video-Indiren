import logging
import os
import shutil
import urllib.request
import zipfile

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DEST_DIR = os.path.join(os.getcwd(), "ffmpeg")
BIN_DIR = os.path.join(DEST_DIR, "bin")


def _notify(progress_callback, phase, progress, message):
    if progress_callback:
        progress_callback(phase, progress, message)


def download_ffmpeg(dest_dir=None, progress_callback=None):
    if dest_dir is None:
        dest_dir = os.path.join(os.getcwd(), "ffmpeg")

    bin_dir = os.path.join(dest_dir, "bin")
    ffmpeg_exe = os.path.join(bin_dir, "ffmpeg.exe")

    if os.path.exists(bin_dir) and os.path.exists(ffmpeg_exe):
        logging.info(f"FFmpeg already installed in: {bin_dir}")
        _notify(progress_callback, "complete", 100, "FFmpeg hazir")
        return

    logging.info("Downloading FFmpeg... (this might take a minute)")
    parent_dir = os.path.dirname(dest_dir)
    zip_path = os.path.join(parent_dir, "ffmpeg.zip") if parent_dir else "ffmpeg.zip"
    temp_extract = os.path.join(parent_dir, "ffmpeg_temp") if parent_dir else "ffmpeg_temp"

    try:
        _notify(progress_callback, "downloading", 0, "FFmpeg indiriliyor...")

        with urllib.request.urlopen(FFMPEG_URL) as response, open(zip_path, "wb") as out_file:
            total_size = int(response.headers.get("Content-Length", "0"))
            downloaded = 0

            while True:
                chunk = response.read(1024 * 128)
                if not chunk:
                    break

                out_file.write(chunk)
                downloaded += len(chunk)

                progress = 0
                if total_size > 0:
                    progress = min(90, int((downloaded / total_size) * 90))

                _notify(progress_callback, "downloading", progress, "FFmpeg indiriliyor...")

        logging.info("Extracting FFmpeg...")
        _notify(progress_callback, "extracting", 92, "FFmpeg arsivi aciliyor...")

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_extract)

        _notify(progress_callback, "extracting", 97, "FFmpeg dosyalari tasiniyor...")

        extracted_folders = os.listdir(temp_extract)
        if not extracted_folders:
            raise RuntimeError("Extraction failed, temp folder empty")

        source_dir = os.path.join(temp_extract, extracted_folders[0])

        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)

        shutil.move(source_dir, dest_dir)

        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(temp_extract):
            shutil.rmtree(temp_extract)

        logging.info(f"FFmpeg installed successfully to: {dest_dir}")
        _notify(progress_callback, "complete", 100, "FFmpeg hazir")

    except Exception as exc:
        logging.error(f"Failed to download/install FFmpeg: {exc}")
        _notify(progress_callback, "failed", 0, f"FFmpeg yukleme hatasi: {exc}")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(temp_extract):
            shutil.rmtree(temp_extract)
        raise


if __name__ == "__main__":
    download_ffmpeg()
