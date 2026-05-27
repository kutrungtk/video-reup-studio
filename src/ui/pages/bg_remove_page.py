"""
Video Reup Studio Rebuild — Background Remove Page
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QFileDialog, QProgressBar, QTextEdit,
    QComboBox,
)
from PySide6.QtCore import QThread, Signal


class BgRemoveWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, input_path, output_path, bg_color):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.bg_color = bg_color

    def run(self):
        try:
            from services.bg_remove import remove_background
            self.progress.emit(30, "Removing background...")
            remove_background(self.input_path, self.output_path, bg_color=self.bg_color)
            self.progress.emit(100, "Done!")
            self.finished.emit(self.output_path)
        except Exception as e:
            self.error.emit(str(e))


class BgRemovePage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header = QLabel("🖼 Background Remove")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)

        # Input
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Input Image:"))
        self._txt_input = QLineEdit()
        self._txt_input.setPlaceholderText("Select image...")
        row1.addWidget(self._txt_input)
        btn = QPushButton("📂")
        btn.setObjectName("SecondaryButton")
        btn.setFixedWidth(36)
        btn.clicked.connect(self._browse)
        row1.addWidget(btn)
        card_layout.addLayout(row1)

        # BG color
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Background:"))
        self._cmb_bg = QComboBox()
        self._cmb_bg.addItems(["Transparent", "Green", "Blue", "Red", "White", "Black"])
        row2.addWidget(self._cmb_bg)
        row2.addStretch()
        card_layout.addLayout(row2)

        # Button
        self._btn_remove = QPushButton("🖼 Remove Background")
        self._btn_remove.setObjectName("PrimaryButton")
        self._btn_remove.setMinimumHeight(36)
        self._btn_remove.clicked.connect(self._remove)
        card_layout.addWidget(self._btn_remove)

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

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select image", filter="Images (*.png *.jpg *.jpeg *.webp);;All (*)")
        if path:
            self._txt_input.setText(path)

    def _remove(self):
        input_path = self._txt_input.text().strip()
        if not input_path:
            return

        import os
        base, _ = os.path.splitext(input_path)
        output_path = f"{base}_nobg.png"
        bg_color = self._cmb_bg.currentText().lower()

        self._btn_remove.setEnabled(False)
        self._progress.setValue(0)
        self._txt_log.clear()

        self._worker = BgRemoveWorker(input_path, output_path, bg_color)
        self._worker.progress.connect(lambda p, m: (self._progress.setValue(p), self._txt_log.append(m)))
        self._worker.finished.connect(lambda p: (
            self._txt_log.append(f"✅ Done: {p}"),
            self._btn_remove.setEnabled(True),
        ))
        self._worker.error.connect(lambda e: (
            self._txt_log.append(f"❌ Error: {e}"),
            self._btn_remove.setEnabled(True),
        ))
        self._worker.start()
