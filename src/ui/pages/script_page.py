"""
Video Reup Studio Rebuild — Script Page
Tab 1: Transcribe + AI Rewrite sub
Tab 2: Dựng kịch bản video (từ sub rewritten → scene descriptions cho visuals)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTextEdit, QFrame, QFileDialog,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar,
)
from PySide6.QtCore import Qt, QThread, Signal

from config.constants import LANGUAGES
from config.settings import get_settings


class ScriptWorker(QThread):
    """Worker for AI rewrite or storyboard generation."""
    progress = Signal(int, str)
    log = Signal(str)
    finished = Signal(str)  # result text
    error = Signal(str)

    def __init__(self, task, srt_path, target_lang, output_path):
        super().__init__()
        self.task = task  # "rewrite" or "storyboard"
        self.srt_path = srt_path
        self.target_lang = target_lang
        self.output_path = output_path

    def run(self):
        try:
            import sys, os
            from config.constants import PROJECT_ROOT
            engine_dir = os.path.join(PROJECT_ROOT, "src", "engine")
            modules_dir = os.path.join(engine_dir, "modules")
            for p in [engine_dir, modules_dir]:
                if p not in sys.path:
                    sys.path.insert(0, p)

            if self.task == "rewrite":
                self._do_rewrite()
            elif self.task == "storyboard":
                self._do_storyboard()

        except Exception as e:
            self.error.emit(str(e))

    def _do_rewrite(self):
        """AI rewrite SRT to target language."""
        from engine.modules.translator import translate_srt
        settings = get_settings()

        self.log.emit(f"Rewriting to {self.target_lang}...")
        self.progress.emit(20, "Calling LLM...")

        translate_srt(
            srt_path=self.srt_path,
            output_path=self.output_path,
            target_lang=self.target_lang,
            llm_endpoint=settings.get("llm_endpoint"),
            model=settings.get("llm_model") or "gemini-2.5-flash",
        )

        self.progress.emit(100, "Done!")
        with open(self.output_path, "r", encoding="utf-8") as f:
            result = f.read()
        self.finished.emit(result)

    def _do_storyboard(self):
        """Generate storyboard from rewritten SRT — output image prompts (EN) for AI gen."""
        from services.llm_client import get_llm
        from config.settings import get_settings

        self.log.emit("Generating storyboard (image prompts) from rewritten SRT...")
        self.progress.emit(10, "Reading SRT...")

        with open(self.srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()

        self.progress.emit(30, "AI creating visual storyboard...")

        settings = get_settings()
        target_duration = settings.get("target_duration") or "60"

        llm = get_llm()
        prompt = f"""You are a visual storyboard director for a short news/storytelling video.

INPUT: A rewritten narration script (subtitle text). The video will be {target_duration} seconds.

YOUR JOB: Create a visual storyboard — decide what IMAGE should appear on screen for each scene.
Every scene WILL use an AI-generated image. There is NO original video. You are creating a NEW video entirely from AI images + voiceover.

RULES:
- Output ONLY in English (image prompts must be in English for the AI image generator)
- Each scene = 1 AI-generated image that visually represents what the narration is talking about
- Image prompts should be DESCRIPTIVE and VISUAL: describe what the viewer SEES (not what they hear)
- Include: subject, setting, lighting, mood, composition, camera angle
- Do NOT include text, watermarks, or UI elements in descriptions
- Keep prompts 20-50 words each
- Decide appropriate duration for each scene based on narration length
- Total scenes should cover the full narration naturally (typically 8-15 scenes for a 60s video)

OUTPUT FORMAT (one line per scene, pipe-separated):
SCENE_NUMBER | IMAGE_PROMPT_EN | CAMERA_EFFECT | DURATION_SECONDS

Camera effects: zoom_in, zoom_out, pan_left, pan_right, parallax, static, pulse, slide_up

NARRATION SCRIPT:
{srt_content[:4000]}

OUTPUT:"""

        result = llm.chat(
            messages=[
                {"role": "system", "content": "You are a professional visual storyboard director. Output ONLY in English. Every scene gets an AI image — there is no original video footage."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=3000,
        )

        self.progress.emit(90, "Saving storyboard...")

        # Save storyboard
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(result)

        self.progress.emit(100, "Done!")
        self.finished.emit(result)


class ScriptPage(QWidget):
    """Script page — Rewrite + Storyboard (kịch bản dựng video)."""

    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._srt_path = ""
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QLabel("📝 Script — Rewrite & Kịch bản dựng")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        # Load SRT row
        load_row = QHBoxLayout()
        self._txt_srt_path = QLineEdit()
        self._txt_srt_path.setPlaceholderText("SRT file path (from Source download)...")
        self._txt_srt_path.setReadOnly(True)
        load_row.addWidget(self._txt_srt_path)

        btn_browse = QPushButton("📂 Browse SRT")
        btn_browse.setObjectName("SecondaryButton")
        btn_browse.clicked.connect(self._browse_srt)
        load_row.addWidget(btn_browse)
        layout.addLayout(load_row)

        # Tabs: Rewrite | Storyboard
        tabs = QTabWidget()
        tabs.addTab(self._create_rewrite_tab(), "① Rewrite (dịch/viết lại)")
        tabs.addTab(self._create_storyboard_tab(), "② Kịch bản dựng (visual script)")
        layout.addWidget(tabs, 1)

    # === TAB 1: Rewrite ===
    def _create_rewrite_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Controls
        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("Target:"))
        self._cmb_lang = QComboBox()
        for code, name in LANGUAGES.items():
            self._cmb_lang.addItem(f"{name} ({code.upper()})", code)
        ctrl_row.addWidget(self._cmb_lang)

        self._btn_rewrite = QPushButton("🤖 AI Rewrite")
        self._btn_rewrite.setObjectName("PrimaryButton")
        self._btn_rewrite.clicked.connect(self._rewrite)
        ctrl_row.addWidget(self._btn_rewrite)

        btn_save = QPushButton("💾 Save")
        btn_save.setObjectName("SecondaryButton")
        btn_save.clicked.connect(self._save_rewritten)
        ctrl_row.addWidget(btn_save)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # Split view
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QFrame()
        left.setObjectName("Card")
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("Original SRT"))
        self._txt_original = QTextEdit()
        self._txt_original.setReadOnly(True)
        self._txt_original.setPlaceholderText("Load SRT file...")
        ll.addWidget(self._txt_original)
        splitter.addWidget(left)

        right = QFrame()
        right.setObjectName("Card")
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("Rewritten SRT"))
        self._txt_rewritten = QTextEdit()
        self._txt_rewritten.setPlaceholderText("AI rewritten text...")
        rl.addWidget(self._txt_rewritten)
        splitter.addWidget(right)

        layout.addWidget(splitter, 1)

        # Progress
        self._progress_rewrite = QProgressBar()
        self._progress_rewrite.setValue(0)
        layout.addWidget(self._progress_rewrite)

        return tab

    # === TAB 2: Storyboard ===
    def _create_storyboard_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        desc = QLabel("Từ SRT đã rewrite → AI tạo kịch bản dựng: mô tả visual, camera move, mood cho từng scene")
        desc.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(desc)

        # Controls
        ctrl_row = QHBoxLayout()
        self._btn_storyboard = QPushButton("🎬 Generate Storyboard")
        self._btn_storyboard.setObjectName("PrimaryButton")
        self._btn_storyboard.clicked.connect(self._generate_storyboard)
        ctrl_row.addWidget(self._btn_storyboard)

        btn_save_sb = QPushButton("💾 Save Storyboard")
        btn_save_sb.setObjectName("SecondaryButton")
        btn_save_sb.clicked.connect(self._save_storyboard)
        ctrl_row.addWidget(btn_save_sb)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # Storyboard table
        self._tbl_storyboard = QTableWidget()
        self._tbl_storyboard.setColumnCount(4)
        self._tbl_storyboard.setHorizontalHeaderLabels(["#", "Image Prompt (EN)", "Camera", "Duration"])
        self._tbl_storyboard.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._tbl_storyboard, 1)

        # Raw text (editable)
        layout.addWidget(QLabel("Raw storyboard (editable):"))
        self._txt_storyboard = QTextEdit()
        self._txt_storyboard.setPlaceholderText(
            "Format: SCENE | VISUAL_DESCRIPTION | CAMERA_MOVE | MOOD\n"
            "VD: 1 | Close-up of smartphone showing breaking news | zoom_in | dramatic"
        )
        self._txt_storyboard.setMaximumHeight(150)
        layout.addWidget(self._txt_storyboard)

        # Progress
        self._progress_sb = QProgressBar()
        self._progress_sb.setValue(0)
        layout.addWidget(self._progress_sb)

        return tab

    # === Actions ===

    def _browse_srt(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SRT file", filter="SRT files (*.srt);;All files (*)")
        if path:
            self._srt_path = path
            self._txt_srt_path.setText(path)
            with open(path, "r", encoding="utf-8") as f:
                self._txt_original.setPlainText(f.read())

    def _rewrite(self):
        if not self._srt_path:
            return

        import os
        output_path = os.path.splitext(self._srt_path)[0] + "_rewritten.srt"
        target_lang = self._cmb_lang.currentData()

        self._btn_rewrite.setEnabled(False)
        self._btn_rewrite.setText("⏳ Rewriting...")
        self._progress_rewrite.setValue(0)

        self._worker = ScriptWorker("rewrite", self._srt_path, target_lang, output_path)
        self._worker.progress.connect(lambda p, m: self._progress_rewrite.setValue(p))
        self._worker.log.connect(lambda m: None)
        self._worker.finished.connect(self._on_rewrite_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_rewrite_done(self, result):
        self._txt_rewritten.setPlainText(result)
        self._btn_rewrite.setEnabled(True)
        self._btn_rewrite.setText("🤖 AI Rewrite")
        self._progress_rewrite.setValue(100)

    def _generate_storyboard(self):
        # Use rewritten SRT if available, otherwise original
        srt_to_use = self._srt_path
        rewritten_text = self._txt_rewritten.toPlainText().strip()
        if rewritten_text:
            import os, tempfile
            # Save rewritten to temp file for storyboard generation
            tmp = os.path.splitext(self._srt_path)[0] + "_rewritten.srt"
            if os.path.isfile(tmp):
                srt_to_use = tmp

        if not srt_to_use:
            return

        import os
        output_path = os.path.splitext(self._srt_path)[0] + "_storyboard.txt"

        self._btn_storyboard.setEnabled(False)
        self._btn_storyboard.setText("⏳ Generating...")
        self._progress_sb.setValue(0)

        self._worker = ScriptWorker("storyboard", srt_to_use, "", output_path)
        self._worker.progress.connect(lambda p, m: self._progress_sb.setValue(p))
        self._worker.log.connect(lambda m: None)
        self._worker.finished.connect(self._on_storyboard_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_storyboard_done(self, result):
        self._txt_storyboard.setPlainText(result)
        self._btn_storyboard.setEnabled(True)
        self._btn_storyboard.setText("🎬 Generate Storyboard")
        self._progress_sb.setValue(100)

        # Parse into table
        self._tbl_storyboard.setRowCount(0)
        for line in result.strip().split("\n"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                row = self._tbl_storyboard.rowCount()
                self._tbl_storyboard.insertRow(row)
                for col, val in enumerate(parts[:4]):
                    self._tbl_storyboard.setItem(row, col, QTableWidgetItem(val))

    def _on_error(self, msg):
        self._btn_rewrite.setEnabled(True)
        self._btn_rewrite.setText("🤖 AI Rewrite")
        self._btn_storyboard.setEnabled(True)
        self._btn_storyboard.setText("🎬 Generate Storyboard")
        self._main.set_status(f"Error: {msg}")

    def _save_rewritten(self):
        text = self._txt_rewritten.toPlainText().strip()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Rewritten SRT", filter="SRT (*.srt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

    def _save_storyboard(self):
        text = self._txt_storyboard.toPlainText().strip()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Storyboard", filter="Text (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

    def load_srt(self, path: str):
        """Load SRT programmatically (called from Source page)."""
        self._srt_path = path
        self._txt_srt_path.setText(path)
        with open(path, "r", encoding="utf-8") as f:
            self._txt_original.setPlainText(f.read())
