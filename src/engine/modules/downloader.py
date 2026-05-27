"""
Video Reup Studio - Downloader Module
Download video + subtitles from YouTube/other platforms via yt-dlp.
Supports cookies for age-restricted/private content.
"""

import os
import json
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DownloadResult:
    """Result of a download operation."""
    video_path: str
    subtitle_path: Optional[str] = None  # SRT if available
    title: str = ""
    duration: float = 0.0
    thumbnail_path: Optional[str] = None
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


def find_ytdlp() -> str:
    """Find yt-dlp binary."""
    ytdlp = shutil.which("yt-dlp")
    if ytdlp:
        return ytdlp
    # Check common locations
    common = [
        os.path.expanduser("~/yt-dlp.exe"),
        os.path.expanduser("~/.local/bin/yt-dlp"),
        r"C:\yt-dlp\yt-dlp.exe",
    ]
    for p in common:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("yt-dlp not found. Install: pip install yt-dlp")


def _find_ffmpeg_dir() -> str:
    """Find directory containing ffmpeg binary (for yt-dlp --ffmpeg-location)."""
    # Check project-local ffmpeg_bin (3 levels up from modules/downloader.py)
    this_dir = os.path.dirname(os.path.abspath(__file__))  # modules/
    engine_dir = os.path.dirname(this_dir)                  # src/engine/
    src_dir = os.path.dirname(engine_dir)                   # src/
    project_root = os.path.dirname(src_dir)                 # project root
    local_dir = os.path.join(project_root, "ffmpeg_bin")
    if os.path.isdir(local_dir) and os.path.isfile(os.path.join(local_dir, "ffmpeg.exe")):
        return local_dir
    # Check imageio_ffmpeg (pip installed) — need to symlink/copy as ffmpeg.exe
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        if os.path.isfile(ffmpeg_path):
            # yt-dlp needs file named "ffmpeg.exe", create one in ffmpeg_bin if missing
            os.makedirs(local_dir, exist_ok=True)
            target = os.path.join(local_dir, "ffmpeg.exe")
            if not os.path.isfile(target):
                import shutil as sh
                sh.copy2(ffmpeg_path, target)
            return local_dir
    except ImportError:
        pass
    # Check PATH
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return os.path.dirname(ffmpeg)
    # Common Windows paths
    for p in [r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin"]:
        if os.path.isdir(p):
            return p
    return ""


def download_video(
    url: str,
    output_dir: str,
    cookies_path: Optional[str] = None,
    subtitle_lang: Optional[str] = None,
    max_resolution: int = 1080,
    prefer_format: str = "mp4",
) -> DownloadResult:
    """
    Download video from URL with optional subtitles.
    
    Args:
        url: Video URL (YouTube, TikTok, etc.)
        output_dir: Directory to save downloaded files
        cookies_path: Path to cookies.txt (for restricted content)
        subtitle_lang: Language code for subtitles (e.g., "en", "vi")
                      None = download all available
        max_resolution: Max video height (1080, 720, etc.)
        prefer_format: Preferred container format
    
    Returns:
        DownloadResult with paths to downloaded files
    """
    os.makedirs(output_dir, exist_ok=True)

    ytdlp = find_ytdlp()

    # Output template
    output_template = os.path.join(output_dir, "source.%(ext)s")

    # Build command
    cmd = [
        ytdlp,
        "--no-playlist",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--no-abort-on-error",
        "--retries", "3",
    ]

    # Add ffmpeg location if available
    ffmpeg_dir = _find_ffmpeg_dir()
    if ffmpeg_dir:
        cmd += ["--ffmpeg-location", ffmpeg_dir]

    cmd += [
        "-f", f"bestvideo[height<={max_resolution}]+bestaudio/best[height<={max_resolution}]",
        "--merge-output-format", prefer_format,
        "-o", output_template,
        "--write-info-json",
    ]

    # Cookies
    if cookies_path and os.path.isfile(cookies_path):
        cmd += ["--cookies", cookies_path]

    # Subtitles
    if subtitle_lang:
        cmd += [
            "--write-sub",
            "--write-auto-sub",
            "--sub-lang", subtitle_lang,
            "--sub-format", "srt",
            "--convert-subs", "srt",
        ]
    else:
        cmd += [
            "--write-sub",
            "--write-auto-sub",
            "--sub-format", "srt",
            "--convert-subs", "srt",
        ]

    # Thumbnail
    cmd += ["--write-thumbnail", "--convert-thumbnails", "jpg"]

    # URL
    cmd.append(url)

    print(f"[Downloader] Downloading: {url}")
    print(f"[Downloader] Output dir: {output_dir}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min max
    )

    if result.returncode != 0:
        error_msg = result.stderr[:500] if result.stderr else "Unknown error"
        # Don't fail if only subtitle download failed (video may still be OK)
        if "Unable to download video subtitles" in error_msg and "ERROR: " not in error_msg.split("subtitles")[0]:
            print(f"[Downloader] Warning: subtitle download failed, continuing with video only")
        else:
            raise RuntimeError(f"yt-dlp failed: {error_msg}")

    # Find downloaded files
    video_path = _find_file(output_dir, "source", [".mp4", ".mkv", ".webm"])
    if not video_path:
        raise FileNotFoundError(f"Downloaded video not found in {output_dir}")

    subtitle_path = _find_subtitle(output_dir)
    thumbnail_path = _find_file(output_dir, "source", [".jpg", ".png", ".webp"])

    # Parse metadata from info json
    metadata = {}
    title = ""
    duration = 0.0
    info_json = _find_file(output_dir, "source", [".info.json"])
    if info_json:
        try:
            with open(info_json, "r", encoding="utf-8") as f:
                info = json.load(f)
            title = info.get("title", "")
            duration = float(info.get("duration", 0))
            metadata = {
                "title": title,
                "uploader": info.get("uploader", ""),
                "upload_date": info.get("upload_date", ""),
                "view_count": info.get("view_count", 0),
                "description": info.get("description", "")[:500],
                "original_url": url,
            }
        except (json.JSONDecodeError, KeyError):
            pass

    print(f"[Downloader] Done: {video_path}")
    if subtitle_path:
        print(f"[Downloader] Subtitle: {subtitle_path}")

    return DownloadResult(
        video_path=video_path,
        subtitle_path=subtitle_path,
        title=title,
        duration=duration,
        thumbnail_path=thumbnail_path,
        metadata=metadata,
    )


def _find_file(directory: str, prefix: str, extensions: list[str]) -> Optional[str]:
    """Find a file matching prefix and extensions in directory."""
    for f in os.listdir(directory):
        for ext in extensions:
            if f.startswith(prefix) and f.endswith(ext):
                return os.path.join(directory, f)
    # Fallback: any file with matching extension
    for f in os.listdir(directory):
        for ext in extensions:
            if f.endswith(ext) and not f.endswith(".info.json"):
                return os.path.join(directory, f)
    return None


def _find_subtitle(directory: str) -> Optional[str]:
    """Find SRT subtitle file in directory."""
    for f in sorted(os.listdir(directory)):
        if f.endswith(".srt"):
            return os.path.join(directory, f)
    return None


def get_video_info_url(url: str, cookies_path: Optional[str] = None) -> dict:
    """
    Get video metadata without downloading.
    Useful for preview/validation before download.
    """
    ytdlp = find_ytdlp()

    cmd = [ytdlp, "--dump-json", "--no-download", "--no-playlist", url]
    if cookies_path and os.path.isfile(cookies_path):
        cmd += ["--cookies", cookies_path]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"Cannot get info: {result.stderr[:200]}")

    return json.loads(result.stdout)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python downloader.py <url> [output_dir] [--cookies path]")
        sys.exit(1)

    url = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "download"
    cookies = None

    for i, arg in enumerate(sys.argv):
        if arg == "--cookies" and i + 1 < len(sys.argv):
            cookies = sys.argv[i + 1]

    result = download_video(url, out_dir, cookies_path=cookies)
    print(f"\nTitle: {result.title}")
    print(f"Video: {result.video_path}")
    print(f"Subtitle: {result.subtitle_path}")
    print(f"Duration: {result.duration:.1f}s")
