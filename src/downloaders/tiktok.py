"""
TikTok downloader — yt-dlp nightly (2026.05.25+) with retry logic.
Handles: tiktok.com, vt.tiktok.com, vm.tiktok.com
"""
import os
import sys
import time
import subprocess


class _SilentLogger:
    """Suppress yt-dlp ERROR output during retry."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def download_tiktok(url: str, output_dir: str, cookie_opts: dict,
                    ffmpeg_location: str, today: str, delay: int = 3,
                    max_retries: int = 3) -> dict:
    """
    Download TikTok video with audio (no watermark).
    
    Strategy:
    - bestvideo+bestaudio merge (yt-dlp nightly solves challenge)
    - Retry up to max_retries times (challenge can be flaky)
    - ffprobe verify audio → fallback to 'download' format if no audio
    
    Returns:
        {'success': bool, 'file': str or None, 'message': str}
    """
    import yt_dlp

    tiktok_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'windowsfilenames': True,
        'encoding': 'utf-8',
        'ffmpeg_location': ffmpeg_location,
        'format': 'bestvideo[height<=1080]+bestaudio/best',
        'merge_output_format': 'mp4',
        'outtmpl': os.path.join(output_dir, f'{today}_%(title).80s.%(ext)s'),
        'logger': _SilentLogger(),
    }
    tiktok_opts.update(cookie_opts)

    if delay > 0:
        tiktok_opts['sleep_interval'] = delay
        tiktok_opts['sleep_requests'] = max(1, delay - 2)

    downloaded_file = None

    def hook(d):
        nonlocal downloaded_file
        if d['status'] == 'finished':
            downloaded_file = d.get('filename', d.get('info_dict', {}).get('_filename', ''))

    tiktok_opts['progress_hooks'] = [hook]

    # Retry download
    for attempt in range(max_retries):
        with yt_dlp.YoutubeDL(tiktok_opts) as ydl:
            ydl.download([url])
        if downloaded_file and os.path.isfile(downloaded_file):
            break
        if attempt < max_retries - 1:
            time.sleep(3)

    if not downloaded_file or not os.path.isfile(downloaded_file):
        return {'success': False, 'file': None, 'message': 'TikTok download failed after retries'}

    # Verify audio with ffprobe
    if not _has_audio(downloaded_file, ffmpeg_location):
        # Try merge audio from 'download' format (watermarked but has audio)
        result = _merge_audio_fallback(url, downloaded_file, output_dir, tiktok_opts, ffmpeg_location)
        return result

    return {'success': True, 'file': downloaded_file, 'message': 'OK'}


def _has_audio(filepath: str, ffmpeg_location: str) -> bool:
    """Check if file has audio stream using ffprobe."""
    try:
        ffprobe = os.path.join(ffmpeg_location, 'ffprobe.exe' if sys.platform == 'win32' else 'ffprobe')
        creationflags = 0x08000000 if sys.platform == 'win32' else 0
        r = subprocess.run(
            [ffprobe, '-v', 'error', '-select_streams', 'a',
             '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', filepath],
            capture_output=True, creationflags=creationflags)
        return 'audio' in r.stdout.decode()
    except Exception:
        return False


def _merge_audio_fallback(url: str, video_file: str, output_dir: str,
                          base_opts: dict, ffmpeg_location: str) -> dict:
    """Download audio from 'download' format and merge with video."""
    import yt_dlp

    audio_tmp = video_file.replace('.mp4', '_audio_tmp.mp4')
    opts_a = {**base_opts, 'outtmpl': audio_tmp, 'format': 'download', 'progress_hooks': []}

    for attempt in range(3):
        with yt_dlp.YoutubeDL(opts_a) as ydl:
            ydl.download([url])
        if os.path.isfile(audio_tmp):
            break
        if attempt < 2:
            time.sleep(3)

    if not os.path.isfile(audio_tmp):
        return {'success': True, 'file': video_file, 'message': 'Video OK, no audio (fallback failed)'}

    # Merge
    final_file = video_file.replace('.mp4', '_merged.mp4')
    ffmpeg = os.path.join(ffmpeg_location, 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')
    creationflags = 0x08000000 if sys.platform == 'win32' else 0
    cmd = [ffmpeg, '-y', '-i', video_file, '-i', audio_tmp,
           '-c:v', 'copy', '-c:a', 'aac', '-map', '0:v:0', '-map', '1:a:0',
           '-shortest', final_file]
    r = subprocess.run(cmd, capture_output=True, creationflags=creationflags)

    # Cleanup
    if os.path.isfile(audio_tmp):
        os.remove(audio_tmp)

    if r.returncode == 0 and os.path.isfile(final_file):
        os.remove(video_file)
        return {'success': True, 'file': final_file, 'message': 'OK (merged audio)'}
    else:
        return {'success': True, 'file': video_file, 'message': 'Video OK, no audio (merge failed)'}
