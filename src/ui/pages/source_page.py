"""
Video Reup Studio Rebuild — Source Page
MỤC ĐÍCH: Tải video + sub từ YouTube URL. Rewrite sub sang ngôn ngữ target.
OUTPUT: source.mp4 + rewritten.srt → sẵn sàng cho bước Voice.
"""

import os
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QTextEdit, QProgressBar,
    QFrame, QFileDialog, QSpinBox,
)
from PySide6.QtCore import Qt, Signal, Slot

from config.constants import LANGUAGES, WORKSPACE_DIR
from config.settings import get_settings


class SourcePage(QWidget):
    """
    Source page — Download video + sub, rewrite sub.
    
    Flow:
    1. Paste URL → Download video + sub
    2. Rewrite sub sang target language (nếu chưa có)
    3. Output: source.mp4 + rewritten.srt
    """

    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._worker = None
        self._project_dir = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QLabel("📥 Source — Tải video & Rewrite sub")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        # === Download Card ===
        dl_card = self._card()
        dl_layout = QVBoxLayout(dl_card)

        dl_layout.addWidget(QLabel("① Tải video + subtitle từ YouTube"))

        # URL input
        url_row = QHBoxLayout()
        self._txt_url = QLineEdit()
        self._txt_url.setPlaceholderText("Paste YouTube URL here...")
        self._txt_url.setMinimumHeight(32)
        url_row.addWidget(self._txt_url)

        btn_browse = QPushButton("📂")
        btn_browse.setObjectName("SecondaryButton")
        btn_browse.setFixedSize(40, 32)
        btn_browse.setToolTip("Browse local video file")
        btn_browse.clicked.connect(self._browse_file)
        url_row.addWidget(btn_browse)
        dl_layout.addLayout(url_row)

        # Options row
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Project name:"))
        self._txt_title = QLineEdit()
        self._txt_title.setPlaceholderText("my-video")
        self._txt_title.setMaximumWidth(200)
        opts.addWidget(self._txt_title)

        opts.addWidget(QLabel("Cookies:"))
        self._txt_cookies = QLineEdit()
        self._txt_cookies.setPlaceholderText("cookies.txt")
        self._txt_cookies.setText(get_settings().get("cookies_path"))
        self._txt_cookies.setMaximumWidth(250)
        opts.addWidget(self._txt_cookies)

        btn_ck = QPushButton("...")
        btn_ck.setFixedWidth(28)
        btn_ck.clicked.connect(self._browse_cookies)
        opts.addWidget(btn_ck)
        opts.addStretch()
        dl_layout.addLayout(opts)

        # Download button
        self._btn_download = QPushButton("📥 Download Video + Sub")
        self._btn_download.setObjectName("PrimaryButton")
        self._btn_download.setMinimumHeight(36)
        self._btn_download.clicked.connect(self._download)
        dl_layout.addWidget(self._btn_download)

        layout.addWidget(dl_card)

        # === Rewrite Card ===
        rw_card = self._card()
        rw_layout = QVBoxLayout(rw_card)

        rw_layout.addWidget(QLabel("② Rewrite subtitle sang ngôn ngữ target"))

        rw_row = QHBoxLayout()
        rw_row.addWidget(QLabel("Target:"))
        self._cmb_lang = QComboBox()
        for code, name in LANGUAGES.items():
            self._cmb_lang.addItem(f"{name} ({code.upper()})", code)
        rw_row.addWidget(self._cmb_lang)

        rw_row.addWidget(QLabel("Duration:"))
        self._spn_duration = QSpinBox()
        self._spn_duration.setRange(15, 600)
        self._spn_duration.setValue(60)
        self._spn_duration.setSuffix("s")
        self._spn_duration.setToolTip("Video output bao nhiêu giây → rewrite sub cho vừa")
        rw_row.addWidget(self._spn_duration)

        rw_row.addWidget(QLabel("~"))
        self._lbl_words = QLabel("150 từ")
        self._lbl_words.setStyleSheet("color: #1ed760; font-size: 11px;")
        rw_row.addWidget(self._lbl_words)
        self._spn_duration.valueChanged.connect(lambda v: self._lbl_words.setText(f"~{int(v * 2.5)} từ"))

        self._btn_rewrite = QPushButton("🤖 Rewrite Sub")
        self._btn_rewrite.setObjectName("PrimaryButton")
        self._btn_rewrite.clicked.connect(self._rewrite)
        rw_row.addWidget(self._btn_rewrite)
        rw_row.addStretch()
        rw_layout.addLayout(rw_row)

        # Status labels
        self._lbl_video = QLabel("Video: —")
        self._lbl_video.setStyleSheet("color: #a0a0a0;")
        rw_layout.addWidget(self._lbl_video)

        self._lbl_sub = QLabel("Sub gốc: —")
        self._lbl_sub.setStyleSheet("color: #a0a0a0;")
        rw_layout.addWidget(self._lbl_sub)

        self._lbl_rewritten = QLabel("Rewritten: —")
        self._lbl_rewritten.setStyleSheet("color: #1ed760;")
        rw_layout.addWidget(self._lbl_rewritten)

        layout.addWidget(rw_card)

        # === Progress + Log ===
        self._progress = QProgressBar()
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        self._lbl_step = QLabel("Ready")
        self._lbl_step.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(self._lbl_step)

        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMaximumHeight(180)
        self._txt_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        layout.addWidget(self._txt_log)

        layout.addStretch()

    # === Download ===

    def _download(self):
        url = self._txt_url.text().strip()
        if not url:
            self._log("⚠ Paste YouTube URL trước.")
            return

        # Create project dir
        title = self._txt_title.text().strip() or "video"
        title = title.replace(" ", "_")
        date = datetime.now().strftime("%Y-%m-%d")
        self._project_dir = os.path.join(WORKSPACE_DIR, f"{date}_{title}")
        os.makedirs(self._project_dir, exist_ok=True)

        # Save cookies setting
        get_settings().set("cookies_path", self._txt_cookies.text().strip())

        self._btn_download.setEnabled(False)
        self._btn_download.setText("⏳ Downloading...")
        self._progress.setValue(0)
        self._txt_log.clear()
        self._log(f"Downloading: {url}")
        self._log(f"Project: {self._project_dir}")

        from workers.download_worker import DownloadWorker
        self._worker = DownloadWorker(url, self._project_dir, self._txt_cookies.text().strip())
        self._worker.progress.connect(lambda p, m: (self._progress.setValue(p), self._set_step(m)))
        self._worker.log_message.connect(self._log)
        self._worker.finished.connect(self._on_download_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_download_done(self, result: dict):
        self._btn_download.setEnabled(True)
        self._btn_download.setText("📥 Download Video + Sub")
        self._progress.setValue(100)
        self._set_step("Download complete!")

        video = result.get("video_path", "")
        sub = result.get("subtitle_path", "")

        self._lbl_video.setText(f"Video: {video}")
        self._lbl_sub.setText(f"Sub gốc: {sub or '(không có — sẽ transcribe ở bước Voice)'}")

        self._log(f"\n✅ Download xong!")
        self._log(f"  Video: {video}")
        self._log(f"  Sub: {sub or 'N/A'}")
        self._main.set_status(f"Downloaded: {self._project_dir}")

    # === Rewrite ===

    def _rewrite(self):
        # Find SRT in project dir
        srt_path = self._find_srt()
        if not srt_path:
            self._log("⚠ Chưa có sub. Download video trước hoặc browse SRT file.")
            return

        target_lang = self._cmb_lang.currentData()
        target_duration = self._spn_duration.value()
        max_words = int(target_duration * 2.5)
        output_path = os.path.join(self._project_dir, "rewritten.srt")

        self._btn_rewrite.setEnabled(False)
        self._btn_rewrite.setText("⏳ Rewriting...")
        self._progress.setValue(0)
        self._log(f"Rewriting to {target_lang}, target {target_duration}s (~{max_words} từ)...")

        from workers.rewrite_worker import RewriteWorker
        self._worker = RewriteWorker(srt_path, output_path, target_lang, target_duration, max_words)
        self._worker.progress.connect(lambda p, m: (self._progress.setValue(p), self._set_step(m)))
        self._worker.log_message.connect(self._log)
        self._worker.finished.connect(self._on_rewrite_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_rewrite_done(self, output_path: str):
        self._btn_rewrite.setEnabled(True)
        self._btn_rewrite.setText("🤖 Rewrite Sub")
        self._progress.setValue(100)
        self._set_step("Rewrite complete!")
        self._lbl_rewritten.setText(f"Rewritten: {output_path}")
        self._log(f"\n✅ Rewrite xong: {output_path}")
        self._log("→ Chuyển sang tab Voice để tạo giọng nói.")
        self._main.set_status("Rewrite done — ready for Voice")

    # === Helpers ===

    def _on_error(self, msg: str):
        self._btn_download.setEnabled(True)
        self._btn_download.setText("📥 Download Video + Sub")
        self._btn_rewrite.setEnabled(True)
        self._btn_rewrite.setText("🤖 Rewrite Sub")
        self._set_step("Error")
        self._log(f"\n❌ Error: {msg}")
        self._main.set_status("Error")

    def _find_srt(self) -> str:
        """Find SRT file in project dir."""
        if not self._project_dir:
            return ""
        for f in os.listdir(self._project_dir):
            if f.endswith(".srt") and "rewritten" not in f:
                return os.path.join(self._project_dir, f)
        return ""

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select video", filter="Video (*.mp4 *.mkv *.avi *.mov *.webm);;All (*)")
        if path:
            self._txt_url.setText(path)

    def _browse_cookies(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select cookies.txt", filter="Text (*.txt);;All (*)")
        if path:
            self._txt_cookies.setText(path)
            get_settings().set("cookies_path", path)

    def _log(self, text: str):
        self._txt_log.append(text)

    def _set_step(self, text: str):
        self._lbl_step.setText(text)

    def _card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        return card

    @property
    def project_dir(self) -> str:
        return self._project_dir
