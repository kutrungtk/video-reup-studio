"""
Video Reup Studio Rebuild — Preview Widget
Video player + Image viewer with subtitle overlay and transport controls.
"""

import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame, QSizePolicy, QStackedWidget,
)
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget


class PreviewWidget(QWidget):
    """Video/Image preview with playback controls."""

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._duration = 0
        self._mode = "video"  # "video" or "image"

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Stacked display: video OR image
        self._display_stack = QStackedWidget()
        self._display_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Video display (index 0)
        self._video_widget = QVideoWidget()
        self._video_widget.setStyleSheet("background: #0a0a0a;")
        self._display_stack.addWidget(self._video_widget)

        # Image display (index 1)
        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background: #0a0a0a;")
        self._image_label.setScaledContents(False)
        self._display_stack.addWidget(self._image_label)

        layout.addWidget(self._display_stack, 1)

        # Subtitle overlay label
        self._lbl_subtitle = QLabel("")
        self._lbl_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_subtitle.setStyleSheet(
            "color: white; font-size: 16px; font-weight: bold; "
            "background: rgba(0,0,0,0.5); padding: 6px 12px; border-radius: 4px;"
        )
        self._lbl_subtitle.setVisible(False)
        layout.addWidget(self._lbl_subtitle)

        # Image info label (filename + dimensions)
        self._lbl_image_info = QLabel("")
        self._lbl_image_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_image_info.setStyleSheet("color: #888; font-size: 10px;")
        self._lbl_image_info.setVisible(False)
        layout.addWidget(self._lbl_image_info)

        # Transport controls
        transport = QHBoxLayout()

        self._btn_play = QPushButton("▶")
        self._btn_play.setObjectName("SecondaryButton")
        self._btn_play.setFixedSize(36, 28)
        self._btn_play.clicked.connect(self._toggle_play)
        transport.addWidget(self._btn_play)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(1000)
        self._slider.sliderMoved.connect(self._seek)
        transport.addWidget(self._slider)

        self._lbl_time = QLabel("0:00 / 0:00")
        self._lbl_time.setStyleSheet("color: #a0a0a0; font-size: 11px; min-width: 80px;")
        transport.addWidget(self._lbl_time)

        layout.addLayout(transport)

        # Media player
        self._player = QMediaPlayer()
        self._audio = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video_widget)
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)

    def load_video(self, path: str):
        """Load video file for preview."""
        self._mode = "video"
        self._display_stack.setCurrentIndex(0)
        self._lbl_image_info.setVisible(False)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.pause()
        self._btn_play.setEnabled(True)
        self._slider.setEnabled(True)

    def load_image(self, path: str):
        """Load image file for preview."""
        self._mode = "image"
        self._display_stack.setCurrentIndex(1)

        # Stop video if playing
        self._player.stop()

        # Load and scale pixmap
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            # Scale to fit while keeping aspect ratio
            scaled = pixmap.scaled(
                self._image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._image_label.setPixmap(scaled)

            # Show info
            fname = os.path.basename(path)
            self._lbl_image_info.setText(f"{fname} — {pixmap.width()}×{pixmap.height()}")
            self._lbl_image_info.setVisible(True)
        else:
            self._image_label.setText("⚠ Cannot load image")
            self._lbl_image_info.setVisible(False)

        # Disable video controls
        self._btn_play.setEnabled(False)
        self._slider.setEnabled(False)
        self._lbl_time.setText("Image")

    def load_file(self, path: str):
        """Auto-detect file type and load appropriately."""
        if not path or not os.path.isfile(path):
            return
        ext = os.path.splitext(path)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"):
            self.load_image(path)
        elif ext in (".mp4", ".mkv", ".webm", ".avi", ".mov"):
            self.load_video(path)

    def seek_to(self, seconds: float):
        """Seek to position in seconds."""
        if self._mode == "video":
            self._player.setPosition(int(seconds * 1000))

    def set_subtitle(self, text: str):
        """Show subtitle text overlay."""
        if text:
            self._lbl_subtitle.setText(text)
            self._lbl_subtitle.setVisible(True)
        else:
            self._lbl_subtitle.setVisible(False)

    def get_position(self) -> float:
        """Get current position in seconds."""
        if self._mode == "video":
            return self._player.position() / 1000.0
        return 0.0

    def _toggle_play(self):
        if self._mode != "video":
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._btn_play.setText("▶")
        else:
            self._player.play()
            self._btn_play.setText("⏸")

    def _seek(self, value):
        if self._mode != "video":
            return
        if self._duration > 0:
            pos = int(value / 1000.0 * self._duration)
            self._player.setPosition(pos)

    def _on_position(self, pos):
        if self._duration > 0:
            self._slider.blockSignals(True)
            self._slider.setValue(int(pos / self._duration * 1000))
            self._slider.blockSignals(False)
        self._lbl_time.setText(f"{self._fmt(pos)} / {self._fmt(self._duration)}")

    def _on_duration(self, dur):
        self._duration = dur

    @staticmethod
    def _fmt(ms: int) -> str:
        s = ms // 1000
        m = s // 60
        s = s % 60
        return f"{m}:{s:02d}"
