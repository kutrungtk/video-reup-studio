"""
Video Reup Studio Rebuild — Batch Resize Page
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QFileDialog, QProgressBar, QTextEdit,
    QComboBox, QListWidget,
)
from PySide6.QtCore import QThread, Signal

from services.batch_resize import PRESETS, MODES


class BatchResizePage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._files = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QLabel("📐 Batch Resize")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)

        # File list
        row1 = QHBoxLayout()
        self._btn_add = QPushButton("➕ Add Images")
        self._btn_add.setObjectName("SecondaryButton")
        self._btn_add.clicked.connect(self._add_files)
        row1.addWidget(self._btn_add)
        self._btn_clear = QPushButton("🗑 Clear")
        self._btn_clear.setObjectName("SecondaryButton")
        self._btn_clear.clicked.connect(self._clear_files)
        row1.addWidget(self._btn_clear)
        self._lbl_count = QLabel("0 files")
        row1.addWidget(self._lbl_count)
        row1.addStretch()
        card_layout.addLayout(row1)

        self._list = QListWidget()
        self._list.setMaximumHeight(100)
        card_layout.addWidget(self._list)

        # Preset + Mode
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Preset:"))
        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems(list(PRESETS.keys()))
        row2.addWidget(self._cmb_preset)

        row2.addWidget(QLabel("Mode:"))
        self._cmb_mode = QComboBox()
        self._cmb_mode.addItems(["Fit (crop center)", "Pad (add borders)", "Stretch"])
        row2.addWidget(self._cmb_mode)
        card_layout.addLayout(row2)

        # Output dir
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Output:"))
        self._txt_output = QLineEdit()
        self._txt_output.setPlaceholderText("Output folder...")
        row3.addWidget(self._txt_output)
        btn_out = QPushButton("📂")
        btn_out.setObjectName("SecondaryButton")
        btn_out.setFixedWidth(36)
        btn_out.clicked.connect(self._browse_output)
        row3.addWidget(btn_out)
        card_layout.addLayout(row3)

        # Button
        self._btn_resize = QPushButton("📐 Resize All")
        self._btn_resize.setObjectName("PrimaryButton")
        self._btn_resize.setMinimumHeight(36)
        self._btn_resize.clicked.connect(self._resize)
        card_layout.addWidget(self._btn_resize)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        card_layout.addWidget(self._progress)

        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMaximumHeight(100)
        self._txt_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        card_layout.addWidget(self._txt_log)

        layout.addWidget(card)
        layout.addStretch()

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select images", filter="Images (*.png *.jpg *.jpeg *.webp *.bmp);;All (*)")
        if paths:
            self._files.extend(paths)
            self._list.clear()
            for p in self._files:
                import os
                self._list.addItem(os.path.basename(p))
            self._lbl_count.setText(f"{len(self._files)} files")

    def _clear_files(self):
        self._files.clear()
        self._list.clear()
        self._lbl_count.setText("0 files")

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select output folder")
        if path:
            self._txt_output.setText(path)

    def _resize(self):
        if not self._files:
            return
        output_dir = self._txt_output.text().strip()
        if not output_dir:
            self._txt_log.append("⚠ Select output folder first")
            return

        preset_name = self._cmb_preset.currentText()
        size = PRESETS[preset_name]
        mode_idx = self._cmb_mode.currentIndex()
        mode = MODES[mode_idx]

        self._btn_resize.setEnabled(False)
        self._progress.setValue(0)
        self._txt_log.clear()
        self._txt_log.append(f"Resizing {len(self._files)} images to {preset_name} ({mode})...")

        # Run in QThread for thread-safe UI updates
        from services.batch_resize import resize_batch
        from PySide6.QtCore import QThread, Signal

        class _ResizeWorker(QThread):
            done = Signal(int, int)  # (success, total)

            def __init__(self, files, output_dir, size, mode):
                super().__init__()
                self._files = files
                self._output_dir = output_dir
                self._size = size
                self._mode = mode

            def run(self):
                results = resize_batch(self._files, self._output_dir, self._size, self._mode)
                ok = sum(1 for r in results if r)
                self.done.emit(ok, len(self._files))

        def _on_resize_done(ok, total):
            self._txt_log.append(f"✅ Done: {ok}/{total} resized")
            self._btn_resize.setEnabled(True)
            self._progress.setValue(100)

        self._resize_worker = _ResizeWorker(self._files, output_dir, size, mode)
        self._resize_worker.done.connect(_on_resize_done)
        self._resize_worker.start()
