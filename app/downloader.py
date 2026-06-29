import os
import sys
import uuid
import shutil
import logging
import yt_dlp
import anyio

from .state import state
from .utils import strip_ansi, format_bytes, time_to_seconds

logger = logging.getLogger(__name__)


def progress_hook(d):
    if state.cancel_requested:
        raise ValueError("DOWNLOAD_CANCELLED")

    if d['status'] == 'downloading':
        p = strip_ansi(d.get('_percent_str', '0%')).strip()
        s = strip_ansi(d.get('_speed_str', '0KB/s')).strip()
        filename = d.get('filename')

        dl = d.get('downloaded_bytes', 0)
        total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
        size_info = f"{format_bytes(dl)} / {format_bytes(total)}"

        info_dict = d.get('info_dict', {})
        playlist_index = d.get('playlist_index') or info_dict.get('playlist_index')
        n_entries = d.get('n_entries') or info_dict.get('n_entries')

        playlist_info = ""
        if playlist_index is not None and n_entries is not None:
            playlist_info = f"{playlist_index} / {n_entries}"

        if filename and filename not in state.current_process_files:
            state.current_process_files.append(filename)

        state.progress_state.update({
            "percent": p,
            "speed": s,
            "size_info": size_info,
            "playlist_info": playlist_info,
            "status": "downloading"
        })
    elif d['status'] == 'finished':
        filename = d.get('filename')
        if filename and filename in state.current_process_files:
            state.current_process_files.remove(filename)

        state.progress_state.update({
            "percent": "100%",
            "speed": "0KB/s",
            "status": "finished"
        })


def postprocessor_hook(d):
    if d['status'] == 'started':
        state.progress_state.update({"status": "merging", "speed": "N/A"})
    elif d['status'] == 'finished':
        state.progress_state.update({"status": "finished", "percent": "100%"})


def build_ydl_opts(url, request, download_dir):
    if request.download_playlist:
        output_template = f"{download_dir}/%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s"
    else:
        output_template = f"{download_dir}/%(title)s [%(id)s].%(ext)s"

    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'nocolor': True,
        'ignoreerrors': request.download_playlist,
        'restrictfilenames': False,
        'progress_hooks': [progress_hook],
        'postprocessor_hooks': [postprocessor_hook],
        'noplaylist': not request.download_playlist,
        'nooverwrites': True,
        'concurrent_fragment_downloads': 10,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'prefer_ffmpeg': True,
        'windows_filenames': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        },
        'format_sort': ['res', 'ext:mp4:m4a'],
        'postprocessor_args': {
            'merger': ['-c', 'copy', '-movflags', '+faststart']
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
        if request.quality == "4k":
            fmt = 'bestvideo[vcodec^=avc1][height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4][height<=2160]/best[height<=2160]/best'
        elif request.quality == "1080p":
            fmt = 'bestvideo[vcodec^=avc1][height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4][height<=1080]/best[height<=1080]/best'
        elif request.quality == "720p":
            fmt = 'bestvideo[vcodec^=avc1][height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]/best'
        elif request.quality == "480p":
            fmt = 'bestvideo[vcodec^=avc1][height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4][height<=480]/best[height<=480]/best'
        else:
            fmt = 'bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best'

        ydl_opts['format'] = fmt
        ydl_opts['merge_output_format'] = 'mp4'

    return ydl_opts, output_template


def _attempt_dl(ydl_opts, url, is_playlist=False, download_dir=None):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise ValueError("Video bilgisi alinamadi. Video gizli olabilir, giris gerektirebilir veya site tarafindan engellenmis olabilir.")
        if is_playlist and ('entries' in info or info.get('_type') == 'playlist'):
            playlist_title = info.get('title', 'Playlist')
            from yt_dlp.utils import sanitize_filename
            safe_title = sanitize_filename(playlist_title, restricted=False)
            if download_dir:
                return os.path.join(download_dir, safe_title)
        return ydl.prepare_filename(info)


def _should_try_next_browser(err_msg):
    cookie_error_terms = [
        "cookie",
        "cookies",
        "browser",
        "profile",
        "database",
        "keyring",
        "decrypt",
        "permission denied",
        "access is denied",
    ]

    if any(term in err_msg for term in cookie_error_terms):
        return True

    return "forbidden" in err_msg or "403" in err_msg


def execute_download(url, request, download_dir):
    output_template = None
    ydl_opts = None

    if request.download_playlist:
        try:
            with yt_dlp.YoutubeDL({
                'extract_flat': True,
                'quiet': True,
                'nocheckcertificate': True,
                'ignoreerrors': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }) as ydl_meta:
                meta = ydl_meta.extract_info(url, download=False)
                if meta and 'entries' in meta:
                    count = len(list(meta['entries']))
                    padding = "03d" if count >= 100 else ("02d" if count >= 10 else "s")
                    output_template = f"{download_dir}/%(playlist_title)s/%(playlist_index){padding} - %(title)s.%(ext)s"
                    logger.info(f"Playlist detected with {count} entries. Using padding: {padding}")
        except Exception as e:
            logger.warning(f"Failed to pre-scan playlist for numbering: {e}")

    if output_template is None:
        if request.download_playlist:
            output_template = f"{download_dir}/%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s"
        else:
            output_template = f"{download_dir}/%(title)s [%(id)s].%(ext)s"

    ydl_opts, _ = build_ydl_opts(url, request, download_dir)
    final_opts = ydl_opts.copy()
    final_opts['outtmpl'] = output_template

    browsers = ['edge', 'chrome', 'brave', 'opera', 'firefox']

    try:
        logger.info("Attempting download without browser cookies...")
        return _attempt_dl(final_opts.copy(), url, request.download_playlist, download_dir)
    except Exception as e:
        no_cookie_error = e
        logger.warning(f"Download without browser cookies failed, trying browser cookies: {e}")

    for browser in browsers:
        try:
            current_opts = final_opts.copy()
            current_opts['cookiesfrombrowser'] = (browser,)
            logger.info(f"Attempting download with {browser} cookies...")
            return _attempt_dl(current_opts, url, request.download_playlist, download_dir)
        except Exception as e:
            err_msg = str(e).lower()
            if _should_try_next_browser(err_msg):
                logger.warning(f"Browser {browser} failed with a retryable cookie/browser error, trying next...")
                continue
            else:
                break

    raise no_cookie_error


async def run_download(url, request, download_dir):
    download_id = str(uuid.uuid4())[:8]
    state.reset_for_download()

    logger.info(f"Received download request for URL: {url} (ID: {download_id}, Quality: {request.quality}, Audio: {request.audio_only}, Playlist: {request.download_playlist})")

    needs_trim = False
    trim_start_sec = 0
    trim_end_sec = None
    if request.start_time or request.end_time:
        s = time_to_seconds(request.start_time)
        e = time_to_seconds(request.end_time)
        trim_start_sec = s if s is not None else 0
        trim_end_sec = e
        if trim_start_sec > 0 or trim_end_sec is not None:
            needs_trim = True

    try:
        logger.info(f"Starting download for ID: {download_id}")
        filename = await anyio.to_thread.run_sync(lambda: execute_download(url, request, download_dir))

        if not os.path.exists(filename):
            base = os.path.splitext(filename)[0]
            for ext in ['mp4', 'mkv', 'webm', 'mp3']:
                if os.path.exists(f"{base}.{ext}"):
                    filename = f"{base}.{ext}"
                    break

        full_path = os.path.abspath(filename)
        logger.info(f"Download successful for ID: {download_id}. Saved to: {full_path}")

        if needs_trim and os.path.exists(full_path) and not state.cancel_requested:
            from .ffmpeg_manager import trim_video_ffmpeg
            trimmed_path = await anyio.to_thread.run_sync(
                lambda: trim_video_ffmpeg(full_path, trim_start_sec, trim_end_sec)
            )
            if trimmed_path and os.path.exists(trimmed_path):
                full_path = os.path.abspath(trimmed_path)
                filename = trimmed_path
                logger.info(f"Trimmed video saved to: {full_path}")

        if filename in state.current_process_files:
            state.current_process_files.remove(filename)

        return {
            "status": "success",
            "message": "Video downloaded successfully",
            "filename": os.path.basename(filename),
            "full_path": full_path
        }

    except Exception as e:
        if state.cancel_requested or "DOWNLOAD_CANCELLED" in str(e):
            logger.info(f"Download {download_id} was cancelled by user.")
            state.progress_state["status"] = "cancelled"
            from .ffmpeg_manager import cleanup_interrupted_downloads
            cleanup_interrupted_downloads(download_dir)
            return {"status": "cancelled", "message": "İndirme iptal edildi"}

        logger.error(f"Download error for ID {download_id}: {str(e)}", exc_info=True)
        print(f"Download error: {str(e)}")
        state.progress_state["status"] = "error"
        raise e


def get_video_info(url):
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'skip_download': True,
            'playlist_items': '1',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info and 'entries' in info:
                entries = [entry for entry in info['entries'] if entry]
                if entries:
                    first_entry = entries[0]
                    duration = first_entry.get('duration', 0)
                    title = first_entry.get('title') or info.get('title') or 'Playlist'
                else:
                    duration = 0
                    title = "Empty Playlist"
            else:
                duration = info.get('duration', 0) if info else 0
                title = info.get('title') if info else None
                if not title:
                    title = info.get('fulltitle') if info else None
                if not title:
                    title = 'Unknown Title'

            return {
                "status": "success",
                "duration": duration,
                "title": title
            }
    except Exception as e:
        logger.error(f"Failed to fetch video info: {str(e)}")
        return {"status": "error", "message": str(e)}
