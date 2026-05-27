"""
Video Reup Studio Rebuild — Upscale Page
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QFileDialog, QProgressBar, QTextEdit,
    QComboBox,
)
from PySide6.QtCore import QThread, Signal


class UpscaleWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, input_path, output_path, target):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.target = target

    def run(self):
        try:
            import os
            from services.upscale import upscale_image, upscale_video
            self.progress.emit(10, "Upscaling...")
            ext = os.path.splitext(self.input_path)[1].lower()
            if ext in (".mp4", ".mkv", ".avi", ".mov", ".webm"):
                upscale_video(self.input_path, self.output_path, target=self.target)
            else:
                upscale_image(self.input_path, self.output_path, target=self.target)
            self.progress.emit(100, "Done!")
            self.finished.emit(self.output_path)
        except Exception as e:
            self.error.emit(str(e))


class UpscalePage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QLabel("🔍 Upscale")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)

        # Input
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Input:"))
        self._txt_input = QLineEdit()
        self._txt_input.setPlaceholderText("Image or video file...")
        row1.addWidget(self._txt_input)
        btn = QPushButton("📂")
        btn.setObjectName("SecondaryButton")
        btn.setFixedWidth(36)
        btn.clicked.connect(self._browse)
        row1.addWidget(btn)
        card_layout.addLayout(row1)

        # Target
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Target Resolution:"))
        self._cmb_target = QComboBox()
        self._cmb_target.addItems(["720p", "1080p", "1440p", "2160p"])
        self._cmb_target.setCurrentIndex(1)
        row2.addWidget(self._cmb_target)
        row2.addStretch()
        card_layout.addLayout(row2)

        # Button
        self._btn_upscale = QPushButton("🔍 Upscale")
        self._btn_upscale.setObjectName("PrimaryButton")
        self._btn_upscale.setMinimumHeight(36)
        self._btn_upscale.clicked.connect(self._upscale)
        card_layout.addWidget(self._btn_upscale)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        card_layout.addWidget(self._progress)

        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMaximumHeight(120)
        self._txt_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        card_layout.addWidget(self._txt_log)

        layout.addWidget(card)
        layout.addStretch()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select file",
            filter="Media (*.mp4 *.mkv *.png *.jpg *.jpeg *.webp);;All (*)")
        if path:
            self._txt_input.setText(path)

    def _upscale(self):
        input_path = self._txt_input.text().strip()
        if not input_path:
            return

        import os
        base, ext = os.path.splitext(input_path)
        target = self._cmb_target.currentText()
        output_path = f"{base}_{target}{ext}"

        self._btn_upscale.setEnabled(False)
        self._progress.setValue(0)
        self._txt_log.clear()
        self._txt_log.append(f"Upscaling to {target}: {input_path}")

        self._worker = UpscaleWorker(input_path, output_path, target)
        self._worker.progress.connect(lambda p, m: (self._progress.setValue(p), self._txt_log.append(m)))
        self._worker.finished.connect(lambda p: (
            self._txt_log.append(f"✅ Done: {p}"),
            self._btn_upscale.setEnabled(True),
        ))
        self._worker.error.connect(lambda e: (
            self._txt_log.append(f"❌ Error: {e}"),
            self._btn_upscale.setEnabled(True),
        ))
        self._worker.start()
