"""
Video Reup Studio Rebuild — Watermark Remove Page
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QFileDialog, QProgressBar, QTextEdit,
    QCheckBox, QSpinBox, QComboBox,
)
from PySide6.QtCore import Qt, QThread, Signal


class WatermarkWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, input_path, output_path, region, is_video):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.region = region
        self.is_video = is_video

    def run(self):
        try:
            from services.watermark_remove import remove_watermark_image, remove_watermark_video
            if self.is_video:
                self.progress.emit(10, "Processing video frames...")
                remove_watermark_video(self.input_path, self.output_path, region=self.region)
            else:
                self.progress.emit(50, "Inpainting...")
                remove_watermark_image(self.input_path, self.output_path, region=self.region)
            self.progress.emit(100, "Done!")
            self.finished.emit(self.output_path)
        except Exception as e:
            self.error.emit(str(e))


class WatermarkPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QLabel("🧹 Watermark Remove")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)

        # Input file
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Input (image/video):"))
        self._txt_input = QLineEdit()
        self._txt_input.setPlaceholderText("Select image or video file...")
        row1.addWidget(self._txt_input)
        btn = QPushButton("📂")
        btn.setObjectName("SecondaryButton")
        btn.setFixedWidth(36)
        btn.clicked.connect(self._browse_input)
        row1.addWidget(btn)
        card_layout.addLayout(row1)

        # Region settings
        card_layout.addWidget(QLabel("Watermark Region:"))
        region_row = QHBoxLayout()
        self._chk_auto = QCheckBox("Auto-detect (bottom-right corner)")
        self._chk_auto.setChecked(True)
        region_row.addWidget(self._chk_auto)
        region_row.addStretch()
        card_layout.addLayout(region_row)

        manual_row = QHBoxLayout()
        for label, attr in [("X:", "_spn_x"), ("Y:", "_spn_y"), ("W:", "_spn_w"), ("H:", "_spn_h")]:
            manual_row.addWidget(QLabel(label))
            spn = QSpinBox()
            spn.setRange(0, 9999)
            spn.setValue(0)
            spn.setEnabled(False)
            setattr(self, attr, spn)
            manual_row.addWidget(spn)
        card_layout.addLayout(manual_row)

        self._chk_auto.toggled.connect(lambda checked: [
            self._spn_x.setEnabled(not checked),
            self._spn_y.setEnabled(not checked),
            self._spn_w.setEnabled(not checked),
            self._spn_h.setEnabled(not checked),
        ])

        # Process button
        self._btn_process = QPushButton("🧹 Remove Watermark")
        self._btn_process.setObjectName("PrimaryButton")
        self._btn_process.setMinimumHeight(36)
        self._btn_process.clicked.connect(self._process)
        card_layout.addWidget(self._btn_process)

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

    def _browse_input(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select file",
            filter="Media files (*.mp4 *.mkv *.avi *.png *.jpg *.jpeg *.webp);;All (*)")
        if path:
            self._txt_input.setText(path)

    def _process(self):
        input_path = self._txt_input.text().strip()
        if not input_path:
            return

        import os
        base, ext = os.path.splitext(input_path)
        output_path = f"{base}_clean{ext}"

        region = None
        if not self._chk_auto.isChecked():
            region = (self._spn_x.value(), self._spn_y.value(),
                      self._spn_w.value(), self._spn_h.value())

        is_video = ext.lower() in (".mp4", ".mkv", ".avi", ".mov", ".webm")

        self._btn_process.setEnabled(False)
        self._progress.setValue(0)
        self._txt_log.clear()
        self._txt_log.append(f"Processing: {input_path}")

        self._worker = WatermarkWorker(input_path, output_path, region, is_video)
        self._worker.progress.connect(lambda p, m: (self._progress.setValue(p), self._txt_log.append(m)))
        self._worker.finished.connect(lambda p: (
            self._txt_log.append(f"✅ Done: {p}"),
            self._btn_process.setEnabled(True),
        ))
        self._worker.error.connect(lambda e: (
            self._txt_log.append(f"❌ Error: {e}"),
            self._btn_process.setEnabled(True),
        ))
        self._worker.start()
