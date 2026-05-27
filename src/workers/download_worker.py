"""
Video Reup Studio Rebuild — Download Worker
QThread worker for downloading video via yt-dlp.
"""

import os
import sys
import traceback
from PySide6.QtCore import QThread, Signal


class DownloadWorker(QThread):
    """Download video in background thread."""

    progress = Signal(int, str)
    log_message = Signal(str)
    finished = Signal(dict)  # {"video_path": ..., "subtitle_path": ...}
    error = Signal(str)

    def __init__(self, url: str, output_dir: str, cookies_path: str = "", parent=None):
        super().__init__(parent)
        self._url = url
        self._output_dir = output_dir
        self._cookies_path = cookies_path

    def run(self):
        try:
            # Add engine to path
            from config.constants import PROJECT_ROOT
            engine_dir = os.path.join(PROJECT_ROOT, "src", "engine")
            modules_dir = os.path.join(engine_dir, "modules")
            for p in [engine_dir, modules_dir]:
                if p not in sys.path:
                    sys.path.insert(0, p)

            self.progress.emit(10, "Starting download...")
            self.log_message.emit(f"URL: {self._url}")
            self.log_message.emit(f"Output: {self._output_dir}")

            from engine.modules.downloader import download_video

            self.progress.emit(30, "Downloading video + subtitles...")

            result = download_video(
                url=self._url,
                output_dir=self._output_dir,
                cookies_path=self._cookies_path if self._cookies_path else None,
            )

            self.progress.emit(90, "Download complete, processing...")

            output = {
                "video_path": result.video_path,
                "subtitle_path": result.subtitle_path or "",
                "title": result.title,
                "duration": result.duration,
            }

            self.log_message.emit(f"Video: {result.video_path}")
            if result.subtitle_path:
                self.log_message.emit(f"Subtitle: {result.subtitle_path}")
            self.log_message.emit(f"Title: {result.title}")
            self.log_message.emit(f"Duration: {result.duration:.1f}s")

            self.progress.emit(100, "Done!")
            self.finished.emit(output)

        except Exception as e:
            tb = traceback.format_exc()
            self.log_message.emit(f"❌ Error: {str(e)}\n{tb}")
            self.error.emit(str(e))
