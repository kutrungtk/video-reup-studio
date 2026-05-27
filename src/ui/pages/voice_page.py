"""
Voice Page — TTS per segment (OmniVoice clone / Edge-TTS)
INPUT: rewritten.srt
OUTPUT: voice_segments/ folder with WAV/MP3 per segment
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame, QFileDialog, QProgressBar,
    QTextEdit, QDoubleSpinBox, QGroupBox, QGridLayout,
)
from PySide6.QtCore import Qt

from config.constants import LANGUAGES


class VoicePage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        layout.addWidget(self._header("🎙 Voice — Tạo giọng nói per segment"))

        # Input
        card = self._card()
        cl = QVBoxLayout(card)
        cl.addWidget(QLabel("Input: SRT đã rewrite (từ bước Source)"))

        row = QHBoxLayout()
        row.addWidget(QLabel("SRT:"))
        self._txt_srt = QLineEdit()
        self._txt_srt.setPlaceholderText("rewritten.srt")
        row.addWidget(self._txt_srt)
        btn = QPushButton("📂")
        btn.setObjectName("SecondaryButton")
        btn.setFixedWidth(36)
        btn.clicked.connect(lambda: self._browse(self._txt_srt, "SRT (*.srt);;All (*)"))
        row.addWidget(btn)
        cl.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Output:"))
        self._txt_output = QLineEdit()
        self._txt_output.setPlaceholderText("voice_segments/")
        row2.addWidget(self._txt_output)
        btn2 = QPushButton("📂")
        btn2.setObjectName("SecondaryButton")
        btn2.setFixedWidth(36)
        btn2.clicked.connect(lambda: self._browse_dir(self._txt_output))
        row2.addWidget(btn2)
        cl.addLayout(row2)
        layout.addWidget(card)

        # Config
        cfg = self._card()
        cfl = QGridLayout(cfg)

        cfl.addWidget(QLabel("Engine:"), 0, 0)
        self._cmb_engine = QComboBox()
        self._cmb_engine.addItem("OmniVoice (CUDA clone)", "omnivoice")
        self._cmb_engine.addItem("Edge-TTS (Free)", "edge-tts")
        cfl.addWidget(self._cmb_engine, 0, 1)

        cfl.addWidget(QLabel("Language:"), 0, 2)
        self._cmb_lang = QComboBox()
        for code, name in LANGUAGES.items():
            self._cmb_lang.addItem(f"{name}", code)
        cfl.addWidget(self._cmb_lang, 0, 3)

        cfl.addWidget(QLabel("Speed:"), 1, 0)
        self._spn_speed = QDoubleSpinBox()
        self._spn_speed.setRange(0.5, 2.0)
        self._spn_speed.setValue(1.0)
        self._spn_speed.setSingleStep(0.1)
        cfl.addWidget(self._spn_speed, 1, 1)

        cfl.addWidget(QLabel("Ref Audio (clone):"), 2, 0)
        ref_row = QHBoxLayout()
        self._txt_ref = QLineEdit()
        self._txt_ref.setPlaceholderText("3s+ audio for voice clone (optional)")
        ref_row.addWidget(self._txt_ref)
        btn_ref = QPushButton("📂")
        btn_ref.setObjectName("SecondaryButton")
        btn_ref.setFixedWidth(36)
        btn_ref.clicked.connect(lambda: self._browse(self._txt_ref, "Audio (*.wav *.mp3 *.m4a);;All (*)"))
        ref_row.addWidget(btn_ref)
        cfl.addLayout(ref_row, 2, 1, 1, 3)

        cfl.addWidget(QLabel("Instruct:"), 3, 0)
        self._txt_instruct = QLineEdit()
        self._txt_instruct.setPlaceholderText("e.g. giọng MC tin tức, rõ ràng")
        cfl.addWidget(self._txt_instruct, 3, 1, 1, 3)

        layout.addWidget(cfg)

        # Button
        btn_row = QHBoxLayout()
        self._btn_gen = QPushButton("🎙 Generate Voice")
        self._btn_gen.setObjectName("PrimaryButton")
        self._btn_gen.setMinimumHeight(36)
        self._btn_gen.clicked.connect(self._generate)
        btn_row.addWidget(self._btn_gen)
        self._btn_cancel = QPushButton("⏹ Cancel")
        self._btn_cancel.setObjectName("SecondaryButton")
        self._btn_cancel.setVisible(False)
        self._btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self._btn_cancel)
        layout.addLayout(btn_row)

        self._progress = QProgressBar()
        layout.addWidget(self._progress)

        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMaximumHeight(150)
        self._txt_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        layout.addWidget(self._txt_log)
        layout.addStretch()

    def _generate(self):
        srt = self._txt_srt.text().strip()
        if not srt:
            self._txt_log.append("⚠ Select SRT file")
            return
        output = self._txt_output.text().strip()
        if not output:
            import os
            output = os.path.join(os.path.dirname(srt), "voice_segments")
            self._txt_output.setText(output)

        from config.settings import get_settings
        config = {
            "engine": self._cmb_engine.currentData(),
            "language": self._cmb_lang.currentData(),
            "speed": self._spn_speed.value(),
            "ref_audio": self._txt_ref.text().strip(),
            "instruct": self._txt_instruct.text().strip(),
            "device": "cuda",
            "edge_voice": get_settings().get("edge_tts_voice"),
        }

        self._btn_gen.setEnabled(False)
        self._btn_gen.setText("⏳ Generating...")
        self._btn_cancel.setVisible(True)
        self._progress.setValue(0)
        self._txt_log.clear()

        from workers.voice_worker import VoiceWorker
        self._worker = VoiceWorker(srt, output, config)
        self._worker.progress.connect(lambda p, m: self._progress.setValue(p))
        self._worker.log_message.connect(lambda m: self._txt_log.append(m))
        self._worker.finished.connect(self._done)
        self._worker.error.connect(self._err)
        self._worker.start()

    def _cancel(self):
        if self._worker: self._worker.cancel()

    def _done(self, path):
        self._btn_gen.setEnabled(True)
        self._btn_gen.setText("🎙 Generate Voice")
        self._btn_cancel.setVisible(False)
        self._progress.setValue(100)
        self._txt_log.append(f"\n✅ Voice segments: {path}")

    def _err(self, msg):
        self._btn_gen.setEnabled(True)
        self._btn_gen.setText("🎙 Generate Voice")
        self._btn_cancel.setVisible(False)
        self._txt_log.append(f"\n❌ {msg}")

    def _browse(self, txt, filt):
        p, _ = QFileDialog.getOpenFileName(self, "Select", filter=filt)
        if p: txt.setText(p)

    def _browse_dir(self, txt):
        p = QFileDialog.getExistingDirectory(self, "Select folder")
        if p: txt.setText(p)

    def _header(self, t):
        l = QLabel(t); l.setObjectName("SectionHeader"); return l

    def _card(self):
        c = QFrame(); c.setObjectName("Card"); return c
