"""
Video Reup Studio Rebuild — Batch Download Page
Download hàng loạt video từ YouTube/Facebook/Douyin/TikTok.
Multi-thread (5-10 luồng song song).

Features:
- Scan nguyên kênh YouTube (không cần cookie)
- Import danh sách URL từ file .txt
- Multi-thread download (configurable 1-10 workers)
- Resolution selection (360p-4K)
- Mode: Video MP4, Audio MP3, Thumbnail JPG
- Progress tracking per video
- Auto-feed vào pipeline (Source page)
"""

import os
import time
import threading
from queue import Queue
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame, QFileDialog, QProgressBar,
    QTextEdit, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QAbstractItemView,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer


class ScanWorker(QThread):
    """Scan channel/playlist for video list."""
    progress = Signal(str)
    video_found = Signal(dict)  # {title, url, duration, views}
    finished = Signal(int)  # total count
    error = Signal(str)

    def __init__(self, url: str, limit: int = 50, cookie_opts: dict = None, douyin_scan_mode: str = "author"):
        super().__init__()
        self.url = url
        self.limit = limit
        self.cookie_opts = cookie_opts or {}
        self.douyin_scan_mode = douyin_scan_mode

    def run(self):
        try:
            import yt_dlp

            # Auto-fix YouTube channel URL
            url = self.url
            if "youtube.com/@" in url and "/videos" not in url and "/shorts" not in url:
                url = url.rstrip("/") + "/videos"

            # Douyin: yt-dlp extractor is broken; use direct API scan.
            if "douyin.com" in url.lower():
                from downloaders.douyin import (
                    scan_author_from_video, extract_aweme_id,
                    load_firefox_cookies, fetch_video_detail,
                )
                mode = self.douyin_scan_mode
                if mode == "video":
                    aweme_id = extract_aweme_id(url)
                    if not aweme_id:
                        self.error.emit("Douyin: không lấy được aweme_id")
                        return
                    detail = fetch_video_detail(aweme_id, load_firefox_cookies())
                    if not detail:
                        self.error.emit("Douyin: không lấy được aweme_detail")
                        return
                    videos = [{
                        'title': detail.get('desc') or aweme_id,
                        'url': f"https://www.douyin.com/video/{aweme_id}",
                        'duration': int((detail.get('duration') or 0) / 1000),
                        'views': (detail.get('statistics') or {}).get('play_count', 0),
                    }]
                else:
                    videos = scan_author_from_video(url, limit=self.limit)
                if not videos:
                    self.error.emit("Douyin: không quét được video/tác giả")
                    return
                for v in videos:
                    self.video_found.emit(v)
                self.finished.emit(len(videos))
                return

            self.progress.emit(f"Scanning: {url}")

            ydl_opts = {
                'extract_flat': 'in_playlist',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'playlistend': self.limit,
            }
            # Add cookie options
            # TikTok scan: skip cookies (extract_flat doesn't need them, can cause lock issues)
            # Douyin scan: NEEDS cookies (s_v_web_id required for API access)
            # Others: use whatever user selected
            is_tiktok_scan = 'tiktok.com' in url.lower()
            is_douyin_scan = 'douyin.com' in url.lower()
            if is_tiktok_scan:
                pass  # TikTok scan works without cookies
            elif is_douyin_scan:
                # Douyin always needs Firefox cookies
                ydl_opts['cookiesfrombrowser'] = ('firefox',)
            else:
                ydl_opts.update(self.cookie_opts)

            count = 0
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    self.error.emit("Cannot extract info from URL")
                    return

                # Iterate lazily — don't list() the generator
                entries = info.get('entries', None)
                if entries is None:
                    # Single video, not a playlist
                    entries = [info]

                for e in entries:
                    if not e or count >= self.limit:
                        break

                    title = e.get('title') or f"Video_{count+1}"
                    video_url = e.get('webpage_url') or e.get('url') or url
                    duration = e.get('duration') or 0
                    views = e.get('view_count') or 0

                    self.video_found.emit({
                        'title': title,
                        'url': video_url,
                        'duration': duration,
                        'views': views,
                    })
                    count += 1
                    if count % 50 == 0:
                        self.progress.emit(f"Found {count} videos...")

            self.finished.emit(count)

        except Exception as e:
            import traceback
            err_msg = str(e)
            # Add more detail for debugging
            if 'Cannot extract' in err_msg or 'Unexpected response' in err_msg:
                err_msg += f" (cookies: {'yes' if self.cookie_opts else 'no'})"
            self.error.emit(err_msg)


class DownloadWorker(QThread):
    """Multi-thread download worker."""
    progress = Signal(int, str, str)  # (row_index, status, detail)
    log = Signal(str)
    all_done = Signal(int, int)  # (success, failed)

    def __init__(self, tasks: list, output_dir: str, resolution: str, mode: str, max_workers: int, cookie_opts: dict = None, delay: int = 0):
        super().__init__()
        self.tasks = tasks  # [{index, url, title}, ...]
        self.output_dir = output_dir
        self.resolution = resolution
        self.mode = mode
        self.max_workers = max_workers
        self.cookie_opts = cookie_opts or {}
        self.delay = delay
        self._cancelled = False

    def run(self):
        import yt_dlp
        from concurrent.futures import ThreadPoolExecutor, as_completed

        os.makedirs(self.output_dir, exist_ok=True)
        success = 0
        failed = 0

        # Resolution mapping
        res_map = {"4K (2160p)": "2160", "2K (1440p)": "1440", "1080p": "1080", "720p": "720", "480p": "480", "360p": "360"}
        res = res_map.get(self.resolution, "1080")

        def download_one(task):
            if self._cancelled:
                return False

            idx = task['index']
            url = task['url']
            title = task.get('title', '')

            self.progress.emit(idx, "⏳ Downloading...", "")

            try:
                from datetime import date
                today = date.today().strftime('%Y-%m-%d')
                
                # Detect platform for specific handling
                is_tiktok = 'tiktok.com' in url.lower()
                is_douyin = 'douyin.com' in url.lower()
                
                opts = {
                    'outtmpl': os.path.join(self.output_dir, f'{today}_%(title)s.%(ext)s'),
                    'retries': 3,
                    'fragment_retries': 3,
                    'extractor_retries': 3,
                }
                
                if is_tiktok or is_douyin:
                    # TikTok/Douyin needs quiet=False to work (impersonation/challenge solving)
                    opts['quiet'] = False
                    opts['no_warnings'] = False
                    opts['ignoreerrors'] = False
                else:
                    opts['quiet'] = True
                    opts['no_warnings'] = True
                    opts['ignoreerrors'] = True
                # Add cookie options
                opts.update(self.cookie_opts)

                # Add delay for anti-block (Douyin/TikTok)
                if self.delay > 0:
                    opts['sleep_interval'] = self.delay
                    opts['sleep_requests'] = max(1, self.delay - 2)

                # Find ffmpeg first — determines format strategy
                import shutil
                from config.constants import PROJECT_ROOT
                ffmpeg_location = None
                for ffmpeg_dir in [
                    os.path.join(PROJECT_ROOT, "ffmpeg_bin"),
                    os.path.join(PROJECT_ROOT, "src", "engine", "modules", "ffmpeg_bin"),
                ]:
                    if os.path.isdir(ffmpeg_dir) and any(
                        f.startswith("ffmpeg") for f in os.listdir(ffmpeg_dir)
                    ):
                        ffmpeg_location = ffmpeg_dir
                        break
                if not ffmpeg_location:
                    ff = shutil.which("ffmpeg")
                    if ff:
                        ffmpeg_location = os.path.dirname(ff)

                if ffmpeg_location:
                    opts['ffmpeg_location'] = ffmpeg_location

                # Format strategy:
                # Có ffmpeg → ưu tiên chất lượng cao (bestvideo+bestaudio, merge)
                # Không ffmpeg → chỉ lấy single-file (best có sẵn)
                # TikTok/Douyin: luôn dùng best (file gộp sẵn, tránh mất tiếng)
                has_ffmpeg = ffmpeg_location is not None

                if self.mode == "Video MP4":
                    if is_tiktok:
                        # TikTok 2-pass: video HD (no watermark) + audio from 'download' format + merge
                        opts['format'] = 'bytevc1_1080p_1281826-0/bytevc1_720p_688444-0/h264_720p_929531-0/best'
                        opts['extractor_args'] = {'tiktok': ['api_hostname=api22-normal-c-alisg.tiktokv.com']}
                    elif has_ffmpeg:
                        # Ưu tiên: video+audio riêng (chất lượng cao nhất) → merge
                        opts['format'] = (
                            f'bestvideo[height<={res}]+bestaudio/'
                            f'best[height<={res}][ext=mp4]/'
                            f'best[height<={res}]/best'
                        )
                    else:
                        # Không ffmpeg: chỉ lấy single-file đã gộp sẵn
                        opts['format'] = f'best[height<={res}][ext=mp4]/best[height<={res}]/best'
                    opts['merge_output_format'] = 'mp4'

                elif self.mode == "Video + Thumbnail":
                    if is_tiktok:
                        opts['format'] = 'bytevc1_1080p_1281826-0/bytevc1_720p_688444-0/h264_720p_929531-0/best'
                        opts['extractor_args'] = {'tiktok': ['api_hostname=api22-normal-c-alisg.tiktokv.com']}
                    elif has_ffmpeg:
                        opts['format'] = (
                            f'bestvideo[height<={res}]+bestaudio/'
                            f'best[height<={res}][ext=mp4]/'
                            f'best[height<={res}]/best'
                        )
                    else:
                        opts['format'] = f'best[height<={res}][ext=mp4]/best[height<={res}]/best'
                    opts['merge_output_format'] = 'mp4'
                    opts['writethumbnail'] = True
                    opts['postprocessors'] = [
                        {'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'},
                    ]

                elif self.mode == "Audio MP3":
                    opts['format'] = 'bestaudio/best'
                    if has_ffmpeg:
                        opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]

                elif self.mode == "Thumbnail Only":
                    opts['skip_download'] = True
                    opts['writethumbnail'] = True
                    if has_ffmpeg:
                        opts['postprocessors'] = [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}]

                downloaded_file = None

                def progress_hook(d):
                    nonlocal downloaded_file
                    if d['status'] == 'finished':
                        downloaded_file = d.get('filename', d.get('info_dict', {}).get('_filename', ''))

                opts['progress_hooks'] = [progress_hook]

                # Fix Unicode filenames on Windows
                import sys
                if sys.platform == 'win32':
                    opts['windowsfilenames'] = True
                    opts['encoding'] = 'utf-8'

                if is_tiktok and has_ffmpeg:
                    # TikTok: yt-dlp nightly (2026.05.25+) solves challenge reliably
                    # Use bestvideo+bestaudio merge for best quality without watermark
                    import subprocess

                    # Suppress ERROR output to console (retry handles failures silently)
                    class _SilentLogger:
                        def debug(self, msg): pass
                        def info(self, msg): pass
                        def warning(self, msg): pass
                        def error(self, msg): pass

                    tiktok_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'ignoreerrors': True,
                        'windowsfilenames': True,
                        'encoding': 'utf-8',
                        'ffmpeg_location': ffmpeg_location,
                        'format': 'bestvideo[height<=1080]+bestaudio/best',
                        'merge_output_format': 'mp4',
                        'outtmpl': os.path.join(self.output_dir, f'{today}_%(title).80s.%(ext)s'),
                        'logger': _SilentLogger(),
                    }
                    tiktok_opts.update(self.cookie_opts)

                    downloaded_file = None
                    def tiktok_hook(d):
                        nonlocal downloaded_file
                        if d['status'] == 'finished':
                            downloaded_file = d.get('filename', d.get('info_dict', {}).get('_filename', ''))
                    tiktok_opts['progress_hooks'] = [tiktok_hook]

                    # Retry up to 3 times (challenge can still be flaky)
                    import time
                    for attempt in range(3):
                        with yt_dlp.YoutubeDL(tiktok_opts) as ydl:
                            ydl.download([url])
                        if downloaded_file and os.path.isfile(downloaded_file):
                            break
                        if attempt < 2:
                            time.sleep(3)

                    if downloaded_file and os.path.isfile(downloaded_file):
                        # Verify audio exists
                        ffprobe_path = os.path.join(ffmpeg_location, 'ffprobe.exe' if sys.platform == 'win32' else 'ffprobe')
                        creationflags = 0x08000000 if sys.platform == 'win32' else 0
                        r_probe = subprocess.run(
                            [ffprobe_path, '-v', 'error', '-select_streams', 'a',
                             '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', downloaded_file],
                            capture_output=True, creationflags=creationflags)
                        has_audio = 'audio' in r_probe.stdout.decode()

                        if has_audio:
                            self.progress.emit(idx, "✅ Done", os.path.basename(downloaded_file))
                            self.log.emit(f"✅ [{idx+1}] {title[:50]}")
                            return True
                        else:
                            # No audio — try merge from 'download' format
                            audio_tmp = os.path.join(self.output_dir, f'_tmp_audio_{idx}.mp4')
                            opts_a = {**tiktok_opts, 'outtmpl': audio_tmp, 'format': 'download',
                                       'progress_hooks': []}
                            for attempt in range(3):
                                with yt_dlp.YoutubeDL(opts_a) as ydl:
                                    ydl.download([url])
                                if os.path.isfile(audio_tmp):
                                    break
                                if attempt < 2:
                                    time.sleep(3)

                            if os.path.isfile(audio_tmp):
                                final_file = downloaded_file.replace('.mp4', '_merged.mp4')
                                cmd = [os.path.join(ffmpeg_location, 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg'),
                                       '-y', '-i', downloaded_file, '-i', audio_tmp,
                                       '-c:v', 'copy', '-c:a', 'aac', '-map', '0:v:0', '-map', '1:a:0',
                                       '-shortest', final_file]
                                r = subprocess.run(cmd, capture_output=True, creationflags=creationflags)
                                os.remove(audio_tmp)
                                if r.returncode == 0 and os.path.isfile(final_file):
                                    os.remove(downloaded_file)
                                    self.progress.emit(idx, "✅ Done", os.path.basename(final_file))
                                    self.log.emit(f"✅ [{idx+1}] {title[:50]}")
                                    return True
                                else:
                                    # Merge failed — keep video without audio
                                    self.progress.emit(idx, "⚠️ No audio", os.path.basename(downloaded_file))
                                    self.log.emit(f"⚠️ [{idx+1}] {title[:50]}: Video OK, no audio")
                                    return True
                            else:
                                # Audio download failed — keep video without audio
                                self.progress.emit(idx, "⚠️ No audio", os.path.basename(downloaded_file))
                                self.log.emit(f"⚠️ [{idx+1}] {title[:50]}: Video OK, no audio")
                                return True
                    else:
                        self.progress.emit(idx, "❌ Failed", "TikTok download failed after 3 retries")
                        self.log.emit(f"❌ [{idx+1}] {title[:50]}: TikTok download failed")
                        return False
                elif is_douyin:
                    # Douyin: direct API downloader (jiji262 flow: Firefox cookies + XBogus/ABogus)
                    from downloaders.douyin import download_douyin
                    result_dy = download_douyin(
                        url=url,
                        output_dir=self.output_dir,
                        ffmpeg_location=ffmpeg_location,
                        today=today,
                        delay=self.delay if self.delay > 0 else 5,
                        max_retries=3,
                    )
                    if result_dy.get('success'):
                        file_path = result_dy.get('file') or ''
                        self.progress.emit(idx, "✅ Done", os.path.basename(file_path))
                        self.log.emit(f"✅ [{idx+1}] {title[:50]}")
                        return True
                    else:
                        msg = result_dy.get('message', 'Douyin download failed')
                        self.progress.emit(idx, "❌ Failed", msg[:50])
                        self.log.emit(f"❌ [{idx+1}] {title[:50]}: {msg}")
                        return False
                else:
                    # Standard download (YouTube, FB, IG, etc.)
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        result = ydl.download([url])

                # Verify file actually exists
                if downloaded_file and os.path.isfile(downloaded_file):
                    self.progress.emit(idx, "✅ Done", os.path.basename(downloaded_file))
                    self.log.emit(f"✅ [{idx+1}] {title[:50]}")
                    return True
                elif result == 0:
                    # yt-dlp returned 0 but no file hook — check by pattern
                    import glob
                    pattern = os.path.join(self.output_dir, f"{today}*")
                    matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
                    if matches:
                        self.progress.emit(idx, "✅ Done", os.path.basename(matches[0]))
                        self.log.emit(f"✅ [{idx+1}] {title[:50]}")
                        return True
                    else:
                        self.progress.emit(idx, "❌ Failed", "File not saved")
                        self.log.emit(f"❌ [{idx+1}] {title[:50]}: Download reported OK but file not found")
                        return False
                else:
                    self.progress.emit(idx, "❌ Failed", "Download failed")
                    self.log.emit(f"❌ [{idx+1}] {title[:50]}: yt-dlp returned error code {result}")
                    return False

            except Exception as e:
                self.progress.emit(idx, "❌ Error", str(e)[:50])
                self.log.emit(f"❌ [{idx+1}] {title[:30]}: {e}")
                return False

        # Multi-thread download
        self.log.emit(f"🚀 Starting {len(self.tasks)} downloads ({self.max_workers} workers)...")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(download_one, task): task for task in self.tasks}
            for future in as_completed(futures):
                if self._cancelled:
                    break
                if future.result():
                    success += 1
                else:
                    failed += 1

        self.all_done.emit(success, failed)

    def cancel(self):
        self._cancelled = True


class BatchDownloadPage(QWidget):
    """Batch Download — scan channel + multi-thread download."""

    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._scan_worker = None
        self._dl_worker = None
        self._videos = []  # [{title, url, duration, views}, ...]
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QLabel("📥 Batch Download — Tải hàng loạt (Multi-thread)")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        # === URL Input ===
        input_row = QHBoxLayout()
        self._txt_url = QLineEdit()
        self._txt_url.setPlaceholderText("Paste URL kênh YouTube, playlist, hoặc video đơn lẻ...")
        self._txt_url.setMinimumHeight(40)
        input_row.addWidget(self._txt_url)

        btn_txt = QPushButton("📂 TXT")
        btn_txt.setObjectName("SecondaryButton")
        btn_txt.setFixedHeight(40)
        btn_txt.clicked.connect(self._import_txt)
        input_row.addWidget(btn_txt)

        btn_scan = QPushButton("🔍 SCAN")
        btn_scan.setObjectName("PrimaryButton")
        btn_scan.setFixedHeight(40)
        btn_scan.setFixedWidth(120)
        btn_scan.clicked.connect(self._scan)
        self._btn_scan = btn_scan
        input_row.addWidget(btn_scan)

        layout.addLayout(input_row)

        # === Settings Row ===
        settings = QHBoxLayout()

        settings.addWidget(QLabel("Resolution:"))
        self._cmb_res = QComboBox()
        self._cmb_res.addItems(["1080p", "720p", "480p", "360p", "4K (2160p)", "2K (1440p)"])
        settings.addWidget(self._cmb_res)

        settings.addWidget(QLabel("Mode:"))
        self._cmb_mode = QComboBox()
        self._cmb_mode.addItems(["Video MP4", "Video + Thumbnail", "Audio MP3", "Thumbnail Only"])
        settings.addWidget(self._cmb_mode)

        settings.addWidget(QLabel("Douyin:"))
        self._cmb_douyin_mode = QComboBox()
        self._cmb_douyin_mode.addItem("Tác giả/kênh", "author")
        self._cmb_douyin_mode.addItem("Video hiện tại", "video")
        self._cmb_douyin_mode.setToolTip("Douyin: quét cả tác giả từ 1 video, hoặc chỉ tải video hiện tại")
        settings.addWidget(self._cmb_douyin_mode)

        settings.addWidget(QLabel("Workers:"))
        self._spn_workers = QSpinBox()
        self._spn_workers.setRange(1, 20)
        self._spn_workers.setValue(5)
        self._spn_workers.setToolTip("Số luồng tải song song (5-10 recommended)")
        settings.addWidget(self._spn_workers)

        settings.addWidget(QLabel("Delay:"))
        self._spn_delay = QSpinBox()
        self._spn_delay.setRange(0, 30)
        self._spn_delay.setValue(0)
        self._spn_delay.setSuffix("s")
        self._spn_delay.setToolTip("Nghỉ giữa mỗi video (Douyin/TikTok: 3-5s để tránh block)")
        settings.addWidget(self._spn_delay)

        settings.addWidget(QLabel("Limit:"))
        self._spn_limit = QSpinBox()
        self._spn_limit.setRange(1, 2000)
        self._spn_limit.setValue(100)
        self._spn_limit.setToolTip("Giới hạn số video scan")
        settings.addWidget(self._spn_limit)

        settings.addStretch()

        # Cookie option
        settings.addWidget(QLabel("🍪"))
        self._cmb_cookie = QComboBox()
        self._cmb_cookie.addItem("Không cookie", "none")
        self._cmb_cookie.addItem("Firefox", "firefox")
        self._cmb_cookie.addItem("Chrome", "chrome")
        self._cmb_cookie.addItem("Edge", "edge")
        self._cmb_cookie.addItem("File cookie.txt", "file")
        self._cmb_cookie.setToolTip("Cookie cho TikTok/Facebook/Instagram (YouTube không cần)")
        self._cmb_cookie.currentIndexChanged.connect(self._on_cookie_changed)
        settings.addWidget(self._cmb_cookie)

        self._txt_cookie_file = QLineEdit()
        self._txt_cookie_file.setPlaceholderText("cookies.txt")
        self._txt_cookie_file.setFixedWidth(120)
        self._txt_cookie_file.setVisible(False)
        settings.addWidget(self._txt_cookie_file)

        self._btn_cookie_browse = QPushButton("📂")
        self._btn_cookie_browse.setFixedWidth(30)
        self._btn_cookie_browse.setVisible(False)
        self._btn_cookie_browse.clicked.connect(self._browse_cookie)
        settings.addWidget(self._btn_cookie_browse)

        # Output dir
        settings.addWidget(QLabel("Save:"))
        self._txt_output = QLineEdit()
        # Load saved path from settings
        from config.settings import get_settings
        saved_dl_path = get_settings().get("batch_download_dir", "")
        if saved_dl_path and os.path.isdir(saved_dl_path):
            self._txt_output.setText(saved_dl_path)
        else:
            self._txt_output.setText(os.path.join(os.path.expanduser("~"), "Downloads", "VideoReup_Downloads"))
        self._txt_output.setFixedWidth(250)
        settings.addWidget(self._txt_output)
        btn_dir = QPushButton("📂")
        btn_dir.setObjectName("SecondaryButton")
        btn_dir.setFixedWidth(36)
        btn_dir.clicked.connect(self._browse_output)
        settings.addWidget(btn_dir)

        layout.addLayout(settings)

        # === Video Table ===
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["☑", "#", "Title", "Duration", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().resizeSection(0, 40)
        self._table.horizontalHeader().resizeSection(1, 40)
        self._table.horizontalHeader().resizeSection(3, 80)
        self._table.horizontalHeader().resizeSection(4, 120)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet("alternate-background-color: #1a1a2e;")
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table, 1)

        # === Action Row ===
        action_row = QHBoxLayout()

        self._btn_select_all = QPushButton("☑ Select All")
        self._btn_select_all.setObjectName("SecondaryButton")
        self._btn_select_all.clicked.connect(self._toggle_select_all)
        action_row.addWidget(self._btn_select_all)

        self._lbl_count = QLabel("0 videos")
        self._lbl_count.setStyleSheet("color: #888;")
        action_row.addWidget(self._lbl_count)

        action_row.addStretch()

        self._btn_retry = QPushButton("🔄 Retry Failed")
        self._btn_retry.setObjectName("SecondaryButton")
        self._btn_retry.setMinimumHeight(40)
        self._btn_retry.setVisible(False)
        self._btn_retry.clicked.connect(self._retry_failed)
        action_row.addWidget(self._btn_retry)

        self._btn_download = QPushButton("🚀 DOWNLOAD SELECTED")
        self._btn_download.setObjectName("PrimaryButton")
        self._btn_download.setMinimumHeight(40)
        self._btn_download.setMinimumWidth(220)
        self._btn_download.clicked.connect(self._download)
        action_row.addWidget(self._btn_download)

        self._btn_cancel = QPushButton("⏹ Cancel")
        self._btn_cancel.setObjectName("SecondaryButton")
        self._btn_cancel.setVisible(False)
        self._btn_cancel.clicked.connect(self._cancel)
        action_row.addWidget(self._btn_cancel)

        layout.addLayout(action_row)

        # === Progress + Log ===
        self._progress = QProgressBar()
        self._progress.setMaximumHeight(16)
        layout.addWidget(self._progress)

        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMaximumHeight(100)
        self._txt_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        layout.addWidget(self._txt_log)

    # === Actions ===

    def _scan(self):
        url = self._txt_url.text().strip()
        if not url:
            self._txt_log.append("⚠ Paste URL trước")
            return

        # Auto-detect platform → suggest settings
        url_lower = url.lower()
        if "douyin.com" in url_lower:
            if self._spn_delay.value() < 3:
                self._spn_delay.setValue(5)
                self._txt_log.append("💡 Douyin detected → Delay=5s (chống block)")
            if self._spn_workers.value() > 3:
                self._spn_workers.setValue(2)
                self._txt_log.append("💡 Douyin detected → Workers=2 (an toàn)")
            mode_label = self._cmb_douyin_mode.currentText()
            self._txt_log.append(f"💡 Douyin mode → {mode_label}")
            if self._cmb_cookie.currentData() == "none":
                self._txt_log.append("⚠️ Douyin cần cookie Firefox — hãy mở douyin.com trong Firefox trước")
        elif "tiktok.com" in url_lower:
            if self._spn_delay.value() < 2:
                self._spn_delay.setValue(3)
                self._txt_log.append("💡 TikTok detected → Delay=3s")
            # TikTok: app auto-handles cookies in download (2-pass), no user action needed
        elif "instagram.com" in url_lower:
            if self._cmb_cookie.currentData() == "none":
                self._txt_log.append("⚠️ Instagram cần cookie! Chọn Firefox trong dropdown 🍪")
        elif "facebook.com" in url_lower or "fb.watch" in url_lower:
            if self._cmb_cookie.currentData() == "none":
                self._txt_log.append("💡 Facebook: cookie giúp tải HD + bypass login wall")

        self._videos.clear()
        self._table.setRowCount(0)
        self._btn_scan.setEnabled(False)
        self._btn_scan.setText("⏳ Scanning...")
        self._txt_log.append(f"🔍 Scanning: {url}")

        self._scan_worker = ScanWorker(url, self._spn_limit.value(), self._get_cookie_opts(), self._cmb_douyin_mode.currentData())
        self._scan_worker.video_found.connect(self._on_video_found)
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_video_found(self, video: dict):
        self._videos.append(video)
        row = self._table.rowCount()
        self._table.insertRow(row)

        # Checkbox
        chk = QTableWidgetItem("☑")
        chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 0, chk)

        # Index
        idx = QTableWidgetItem(str(row + 1))
        idx.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 1, idx)

        # Title
        self._table.setItem(row, 2, QTableWidgetItem(video['title'][:80]))

        # Duration
        dur = video.get('duration', 0)
        dur_str = f"{dur//60}:{dur%60:02d}" if dur else "N/A"
        dur_item = QTableWidgetItem(dur_str)
        dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 3, dur_item)

        # Status
        status = QTableWidgetItem("Ready")
        status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(row, 4, status)

        self._lbl_count.setText(f"{row + 1} videos")

    def _on_scan_done(self, count):
        self._btn_scan.setEnabled(True)
        self._btn_scan.setText("🔍 SCAN")
        self._txt_log.append(f"✅ Found {count} videos")

    def _on_txt_batch_done(self, count):
        """After scanning one URL from txt, scan next if available."""
        self._txt_log.append(f"  ✅ +{count} videos")
        if hasattr(self, '_pending_urls') and self._pending_urls:
            next_url = self._pending_urls.pop(0)
            self._txt_log.append(f"  🔍 Scanning: {next_url[:60]}...")
            self._scan_worker = ScanWorker(next_url, self._spn_limit.value(), self._get_cookie_opts(), self._cmb_douyin_mode.currentData())
            self._scan_worker.video_found.connect(self._on_video_found)
            self._scan_worker.finished.connect(self._on_txt_batch_done)
            self._scan_worker.error.connect(lambda m: self._txt_log.append(f"  ⚠ {m}"))
            self._scan_worker.start()
        else:
            self._btn_scan.setEnabled(True)
            self._btn_scan.setText("🔍 SCAN")
            self._txt_log.append(f"✅ Done — Total {len(self._videos)} videos")

    def _on_scan_error(self, msg):
        self._btn_scan.setEnabled(True)
        self._btn_scan.setText("🔍 SCAN")
        self._txt_log.append(f"❌ Scan error: {msg}")

    def _download(self):
        # Get selected videos
        tasks = []
        for row in range(self._table.rowCount()):
            chk = self._table.item(row, 0)
            if chk and chk.text() == "☑":
                tasks.append({
                    'index': row,
                    'url': self._videos[row]['url'],
                    'title': self._videos[row]['title'],
                })

        if not tasks:
            self._txt_log.append("⚠ Chọn video trước")
            return

        output_dir = self._txt_output.text().strip()
        resolution = self._cmb_res.currentText()
        mode = self._cmb_mode.currentText()
        workers = self._spn_workers.value()

        self._btn_download.setEnabled(False)
        self._btn_download.setText("⏳ Downloading...")
        self._btn_cancel.setVisible(True)
        self._progress.setValue(0)
        self._txt_log.append(f"🚀 Downloading {len(tasks)} videos ({workers} workers)...")

        self._dl_worker = DownloadWorker(tasks, output_dir, resolution, mode, workers, self._get_cookie_opts(), self._spn_delay.value())
        self._dl_worker.progress.connect(self._on_dl_progress)
        self._dl_worker.log.connect(lambda m: self._txt_log.append(m))
        self._dl_worker.all_done.connect(self._on_dl_done)
        self._dl_worker.start()

    def _on_dl_progress(self, row, status, detail):
        if row < self._table.rowCount():
            self._table.item(row, 4).setText(status)
        # Update progress bar
        done = sum(1 for r in range(self._table.rowCount())
                   if self._table.item(r, 4) and self._table.item(r, 4).text() in ("✅ Done", "❌ Error"))
        total = self._table.rowCount()
        if total > 0:
            self._progress.setValue(int(done / total * 100))

    def _on_dl_done(self, success, failed):
        self._btn_download.setEnabled(True)
        self._btn_download.setText("🚀 DOWNLOAD SELECTED")
        self._btn_cancel.setVisible(False)
        self._progress.setValue(100)
        self._txt_log.append(f"\n✅ Done! Success: {success}, Failed: {failed}")
        self._txt_log.append(f"📂 Saved to: {self._txt_output.text()}")
        # Show retry button if any failed
        if failed > 0:
            self._btn_retry.setVisible(True)

    def _retry_failed(self):
        """Retry only videos with ❌ Failed status."""
        failed_indices = []
        for row in range(self._table.rowCount()):
            status_item = self._table.item(row, 4)
            if status_item and "❌" in status_item.text():
                failed_indices.append(row)
                # Reset status
                status_item.setText("⏳ Retry...")
                # Check the checkbox
                cb = self._table.item(row, 0)
                if cb:
                    cb.setText("☑")

        if not failed_indices:
            self._txt_log.append("ℹ️ No failed videos to retry")
            return

        self._txt_log.append(f"\n🔄 Retrying {len(failed_indices)} failed videos...")
        self._btn_retry.setVisible(False)
        self._download()

    def _cancel(self):
        if self._dl_worker:
            self._dl_worker.cancel()
            self._txt_log.append("⏹ Cancelling...")

    def _on_cell_clicked(self, row, col):
        """Toggle checkbox when clicking column 0."""
        if col == 0:
            item = self._table.item(row, 0)
            if item:
                item.setText("☐" if item.text() == "☑" else "☑")

    def _on_cookie_changed(self, idx):
        is_file = self._cmb_cookie.currentData() == "file"
        self._txt_cookie_file.setVisible(is_file)
        self._btn_cookie_browse.setVisible(is_file)

    def _browse_cookie(self):
        p, _ = QFileDialog.getOpenFileName(self, "Select cookie file", filter="Text (*.txt);;All (*)")
        if p:
            self._txt_cookie_file.setText(p)

    def _get_cookie_opts(self):
        """Return yt-dlp cookie options dict."""
        mode = self._cmb_cookie.currentData()
        if mode == "none":
            # Auto-detect: if URL needs cookies, try firefox automatically
            url = self._txt_url.text().strip().lower()
            needs_cookie = any(p in url for p in ['tiktok.com', 'douyin.com', 'instagram.com', 'facebook.com', 'fb.watch'])
            if needs_cookie:
                # Try firefox first (most reliable on Windows)
                return {'cookiesfrombrowser': ('firefox',)}
            return {}
        elif mode == "file":
            path = self._txt_cookie_file.text().strip()
            if path and os.path.isfile(path):
                return {'cookiefile': path}
            return {}
        else:
            # browser name: firefox, chrome, edge
            return {'cookiesfrombrowser': (mode,)}

    def _toggle_select_all(self):
        all_checked = all(
            self._table.item(r, 0) and self._table.item(r, 0).text() == "☑"
            for r in range(self._table.rowCount())
        )
        new_state = "☐" if all_checked else "☑"
        for r in range(self._table.rowCount()):
            if self._table.item(r, 0):
                self._table.item(r, 0).setText(new_state)

    def _import_txt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import URL list", filter="Text (*.txt);;All (*)")
        if path:
            # Read URLs from file and scan each one
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                if urls:
                    self._txt_url.setText(f"{len(urls)} URLs from {os.path.basename(path)}")
                    self._txt_log.append(f"📂 Loaded {len(urls)} URLs from {path}")
                    # Auto-scan all URLs — scan first URL, queue rest
                    self._videos.clear()
                    self._table.setRowCount(0)
                    self._pending_urls = urls[1:]  # queue remaining
                    self._btn_scan.setEnabled(False)
                    self._btn_scan.setText("⏳ Scanning...")
                    self._scan_worker = ScanWorker(urls[0], self._spn_limit.value(), self._get_cookie_opts(), self._cmb_douyin_mode.currentData())
                    self._scan_worker.video_found.connect(self._on_video_found)
                    self._scan_worker.finished.connect(self._on_txt_batch_done)
                    self._scan_worker.error.connect(self._on_scan_error)
                    self._scan_worker.start()
                else:
                    self._txt_log.append("⚠ File rỗng hoặc không có URL")
            except Exception as e:
                self._txt_log.append(f"❌ Error reading file: {e}")

    def _browse_output(self):
        p = QFileDialog.getExistingDirectory(self, "Select download folder")
        if p:
            self._txt_output.setText(p)
            # Save path for next session
            from config.settings import get_settings
            get_settings().set("batch_download_dir", p)
