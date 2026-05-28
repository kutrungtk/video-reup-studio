"""
Video Reup Studio Rebuild — Thumbnail Pro Page
Pro thumbnail: extract frames, artistic text with effects.
Supports Vietnamese/Japanese/Korean fonts (SVN-Gilroy, Inter).
"""

import os
import subprocess
import tempfile
import shutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame, QFileDialog, QProgressBar,
    QScrollArea, QGridLayout, QSlider, QSpinBox, QColorDialog,
    QSizePolicy, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsItem, QCheckBox, QSplitter,
)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPixmap, QImage, QFont, QColor, QPainter, QPen, QBrush,
    QFontMetrics, QCursor, QPainterPath, QLinearGradient,
    QFontDatabase,
)


def _get_system_fonts():
    """Get all fonts installed on the system, sorted alphabetically."""
    db = QFontDatabase()
    all_fonts = sorted(set(db.families()))
    # Put common video-friendly fonts at top if available
    priority = ["SVN-Gilroy Black", "SVN-Gilroy Heavy", "SVN-Gilroy Bold",
                "Arial Black", "Impact", "Montserrat", "Bebas Neue",
                "Oswald", "Roboto", "Inter", "Arial", "Segoe UI"]
    top = [f for f in priority if f in all_fonts]
    rest = [f for f in all_fonts if f not in top]
    return top + rest


class DraggableText(QGraphicsItem):
    """Pro text with stroke, glow, gradient, shadow, bg box. Draggable."""

    def __init__(self, text, font, color, parent=None):
        super().__init__(parent)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        self._text = text
        self._font = font
        self._color = color
        self._stroke_enabled = True
        self._stroke_color = QColor(0, 0, 0)
        self._stroke_width = 3
        self._shadow_enabled = True
        self._shadow_color = QColor(0, 0, 0, 150)
        self._shadow_offset = QPointF(4, 4)
        self._glow_enabled = False
        self._glow_color = QColor(255, 0, 0, 100)
        self._glow_radius = 8
        self._gradient_enabled = False
        self._gradient_top = QColor(255, 255, 255)
        self._gradient_bottom = QColor(200, 200, 200)
        self._bg_box_enabled = False
        self._bg_box_color = QColor(0, 0, 0, 150)
        self._bg_box_padding = 10
        self._build_path()

    def _build_path(self):
        self._path = QPainterPath()
        self._path.addText(0, QFontMetrics(self._font).ascent(), self._font, self._text)
        self._bounding = self._path.boundingRect().adjusted(-20, -20, 20, 20)

    def set_stroke(self, enabled, color=None, width=None):
        self._stroke_enabled = enabled
        if color:
            self._stroke_color = color
        if width is not None:
            self._stroke_width = width
        self.update()

    def set_shadow(self, enabled, color=None, offset=None):
        self._shadow_enabled = enabled
        if color:
            self._shadow_color = color
        if offset:
            self._shadow_offset = offset
        self.update()

    def set_glow(self, enabled, color=None, radius=None):
        self._glow_enabled = enabled
        if color:
            self._glow_color = color
        if radius is not None:
            self._glow_radius = radius
        self.update()

    def set_gradient(self, enabled, top=None, bottom=None):
        self._gradient_enabled = enabled
        if top:
            self._gradient_top = top
        if bottom:
            self._gradient_bottom = bottom
        self.update()

    def set_bg_box(self, enabled, color=None, padding=None):
        self._bg_box_enabled = enabled
        if color:
            self._bg_box_color = color
        if padding is not None:
            self._bg_box_padding = padding
        self.update()

    def boundingRect(self):
        return self._bounding

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text_rect = self._path.boundingRect()
        if self._bg_box_enabled:
            p = self._bg_box_padding
            painter.fillRect(text_rect.adjusted(-p, -p, p, p), self._bg_box_color)
        if self._glow_enabled:
            for i in range(self._glow_radius, 0, -2):
                gc = QColor(self._glow_color.red(), self._glow_color.green(),
                            self._glow_color.blue(), max(10, self._glow_color.alpha() - i * 10))
                painter.setPen(QPen(gc, i))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(self._path)
        if self._shadow_enabled:
            painter.save()
            painter.translate(self._shadow_offset)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._shadow_color)
            painter.drawPath(self._path)
            painter.restore()
        if self._stroke_enabled and self._stroke_width > 0:
            painter.setPen(QPen(self._stroke_color, self._stroke_width,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._path)
        painter.setPen(Qt.PenStyle.NoPen)
        if self._gradient_enabled:
            grad = QLinearGradient(text_rect.topLeft(), text_rect.bottomLeft())
            grad.setColorAt(0, self._gradient_top)
            grad.setColorAt(1, self._gradient_bottom)
            painter.setBrush(QBrush(grad))
        else:
            painter.setBrush(self._color)
        painter.drawPath(self._path)


class ThumbnailProPage(QWidget):
    """Thumbnail Pro — extract frames + add artistic text with effects."""

    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._video_path = ""
        self._frames = []
        self._selected_frame = ""
        self._text_items = []
        self._current_color = QColor(255, 255, 255)
        self._stroke_color = QColor(0, 0, 0)
        self._glow_color = QColor(255, 0, 0, 100)
        self._gradient_top = QColor(255, 255, 255)
        self._gradient_bottom = QColor(180, 180, 180)
        self._bg_box_color = QColor(0, 0, 0, 150)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QLabel("📸 Thumbnail Pro — Frame + Text Effects")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        # Top: Video input + Extract
        input_row = QHBoxLayout()
        input_row.addWidget(QLabel("Video:"))
        self._txt_video = QLineEdit()
        self._txt_video.setPlaceholderText("Chọn video để trích xuất frames...")
        input_row.addWidget(self._txt_video, 1)

        btn_browse = QPushButton("📂 Chọn Video")
        btn_browse.setStyleSheet("color: white; background: #333; padding: 6px 12px; border-radius: 4px;")
        btn_browse.clicked.connect(self._browse_video)
        input_row.addWidget(btn_browse)

        input_row.addWidget(QLabel("Mỗi:"))
        self._spn_interval = QSpinBox()
        self._spn_interval.setRange(1, 30)
        self._spn_interval.setValue(3)
        self._spn_interval.setSuffix("s")
        input_row.addWidget(self._spn_interval)

        btn_extract = QPushButton("🎬 Extract Frames")
        btn_extract.setStyleSheet("color: white; background: #1ed760; padding: 6px 14px; font-weight: bold; border-radius: 4px;")
        btn_extract.clicked.connect(self._extract_frames)
        input_row.addWidget(btn_extract)
        layout.addLayout(input_row)

        # Splitter: frames left, canvas+controls right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Frame grid
        left = QFrame()
        left.setStyleSheet("background: #111; border-radius: 8px;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.addWidget(QLabel("Frames — click để chọn:"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none;")
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(6)
        scroll.setWidget(self._grid_widget)
        left_layout.addWidget(scroll)
        splitter.addWidget(left)

        # Right: Canvas + controls
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._scene = QGraphicsScene()
        self._view = QGraphicsView(self._scene)
        self._view.setStyleSheet("background: #1a1a1a; border: 1px solid #333; border-radius: 6px;")
        self._view.setMinimumSize(640, 360)
        right_layout.addWidget(self._view, 1)

        # Text controls
        ctrl = QFrame()
        ctrl.setStyleSheet("background: #1a1a2e; border-radius: 8px; padding: 10px;")
        ctrl_layout = QVBoxLayout(ctrl)
        ctrl_layout.setSpacing(8)

        # Row 1: Text + Font + Size + Add + Clear
        row1 = QHBoxLayout()
        self._txt_text = QLineEdit()
        self._txt_text.setPlaceholderText("Nhập text (Việt/Nhật/Hàn OK)...")
        self._txt_text.setText("TIÊU ĐỀ VIDEO")
        row1.addWidget(self._txt_text, 1)

        self._cmb_font = QComboBox()
        self._cmb_font.addItems(_get_system_fonts())
        self._cmb_font.setFixedWidth(160)
        row1.addWidget(self._cmb_font)

        self._spn_size = QSpinBox()
        self._spn_size.setRange(12, 200)
        self._spn_size.setValue(56)
        self._spn_size.setSuffix("px")
        row1.addWidget(self._spn_size)

        btn_add = QPushButton("➕ Add Text")
        btn_add.setStyleSheet("color: white; background: #1ed760; padding: 6px 14px; font-weight: bold; border-radius: 4px;")
        btn_add.clicked.connect(self._add_text)
        row1.addWidget(btn_add)

        btn_clear = QPushButton("🗑 Clear")
        btn_clear.setStyleSheet("color: white; background: #e53935; padding: 6px 10px; border-radius: 4px;")
        btn_clear.clicked.connect(self._clear_texts)
        row1.addWidget(btn_clear)
        ctrl_layout.addLayout(row1)

        # Row 2: Effects
        row2 = QHBoxLayout()
        btn_color = QPushButton("🎨 Color")
        btn_color.setStyleSheet("color: white; background: #444; padding: 4px 10px; border-radius: 4px;")
        btn_color.clicked.connect(self._choose_color)
        row2.addWidget(btn_color)

        self._chk_stroke = QCheckBox("Stroke")
        self._chk_stroke.setChecked(True)
        self._chk_stroke.setStyleSheet("color: white;")
        row2.addWidget(self._chk_stroke)

        btn_stroke_c = QPushButton("⬛")
        btn_stroke_c.setFixedWidth(28)
        btn_stroke_c.setStyleSheet("background: #000; border: 1px solid #555; border-radius: 4px;")
        btn_stroke_c.clicked.connect(self._choose_stroke_color)
        row2.addWidget(btn_stroke_c)

        self._spn_stroke_w = QSpinBox()
        self._spn_stroke_w.setRange(0, 10)
        self._spn_stroke_w.setValue(3)
        self._spn_stroke_w.setPrefix("W:")
        row2.addWidget(self._spn_stroke_w)

        self._chk_shadow = QCheckBox("Shadow")
        self._chk_shadow.setChecked(True)
        self._chk_shadow.setStyleSheet("color: white;")
        row2.addWidget(self._chk_shadow)

        self._chk_glow = QCheckBox("Glow")
        self._chk_glow.setStyleSheet("color: white;")
        row2.addWidget(self._chk_glow)

        btn_glow_c = QPushButton("🔴")
        btn_glow_c.setFixedWidth(28)
        btn_glow_c.setStyleSheet("background: #f00; border-radius: 4px;")
        btn_glow_c.clicked.connect(self._choose_glow_color)
        row2.addWidget(btn_glow_c)

        self._chk_gradient = QCheckBox("Gradient")
        self._chk_gradient.setStyleSheet("color: white;")
        row2.addWidget(self._chk_gradient)

        self._chk_bg_box = QCheckBox("BG Box")
        self._chk_bg_box.setStyleSheet("color: white;")
        row2.addWidget(self._chk_bg_box)

        row2.addStretch()
        ctrl_layout.addLayout(row2)

        # Row 3: Presets + Export
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Preset:"))
        self._cmb_preset = QComboBox()
        self._cmb_preset.addItems([
            "Custom", "YouTube Bold", "Breaking News",
            "Cinematic Gold", "Neon Glow", "Minimal Clean", "Japanese Style",
        ])
        self._cmb_preset.currentIndexChanged.connect(self._apply_preset)
        row3.addWidget(self._cmb_preset)
        row3.addStretch()

        btn_export = QPushButton("💾 Export Thumbnail")
        btn_export.setStyleSheet("color: white; background: #1e88e5; padding: 8px 18px; font-weight: bold; border-radius: 4px;")
        btn_export.clicked.connect(self._export)
        row3.addWidget(btn_export)
        ctrl_layout.addLayout(row3)

        right_layout.addWidget(ctrl)
        splitter.addWidget(right)
        splitter.setSizes([220, 700])
        layout.addWidget(splitter, 1)

    # === Actions ===

    def _find_ffmpeg(self):
        from config.constants import PROJECT_ROOT
        for ffmpeg_dir in [
            os.path.join(PROJECT_ROOT, "ffmpeg_bin"),
            os.path.join(PROJECT_ROOT, "src", "engine", "modules", "ffmpeg_bin"),
        ]:
            candidate = os.path.join(ffmpeg_dir, "ffmpeg.exe")
            if os.path.isfile(candidate):
                return candidate
        ff = shutil.which("ffmpeg")
        return ff if ff else "ffmpeg"

    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video", filter="Video (*.mp4 *.mkv *.webm *.avi *.mov);;All (*)")
        if path:
            self._txt_video.setText(path)
            self._video_path = path

    def _extract_frames(self):
        if not self._video_path or not os.path.isfile(self._video_path):
            self._main.set_status("⚠ Chọn video trước")
            return
        interval = self._spn_interval.value()
        temp_dir = tempfile.mkdtemp(prefix="thumb_frames_")
        ffmpeg_bin = self._find_ffmpeg()
        cmd = [
            ffmpeg_bin, "-i", self._video_path,
            "-vf", f"fps=1/{interval}",
            "-q:v", "2",
            os.path.join(temp_dir, "frame_%04d.jpg"),
            "-y"
        ]
        self._main.set_status("⏳ Extracting frames...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                self._main.set_status(f"❌ FFmpeg error: {result.stderr[:100]}")
                return
        except FileNotFoundError:
            self._main.set_status("❌ ffmpeg not found!")
            return
        except subprocess.TimeoutExpired:
            self._main.set_status("❌ Timeout")
            return
        self._frames = sorted([
            os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.endswith(".jpg")
        ])
        self._populate_frame_grid()
        self._main.set_status(f"✅ Extracted {len(self._frames)} frames")

    def _populate_frame_grid(self):
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        cols = 3
        for i, frame_path in enumerate(self._frames):
            thumb = QLabel()
            thumb.setFixedSize(140, 80)
            thumb.setCursor(Qt.CursorShape.PointingHandCursor)
            thumb.setStyleSheet("border: 2px solid #333; border-radius: 4px;")
            pixmap = QPixmap(frame_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(140, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                thumb.setPixmap(scaled)
            thumb.mousePressEvent = lambda e, p=frame_path, t=thumb: self._select_frame(p, t)
            self._grid_layout.addWidget(thumb, i // cols, i % cols)

    def _select_frame(self, path, thumb_widget=None):
        self._selected_frame = path
        for i in range(self._grid_layout.count()):
            item = self._grid_layout.itemAt(i)
            if item and item.widget():
                item.widget().setStyleSheet("border: 2px solid #333; border-radius: 4px;")
        if thumb_widget:
            thumb_widget.setStyleSheet("border: 2px solid #1ed760; border-radius: 4px;")
        self._scene.clear()
        self._text_items.clear()
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            view_size = self._view.size()
            scaled = pixmap.scaled(
                view_size.width() - 20, view_size.height() - 20,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._scene.addPixmap(scaled)
            self._scene.setSceneRect(QRectF(scaled.rect()))

    def _add_text(self):
        text = self._txt_text.text().strip()
        if not text:
            return
        font_name = self._cmb_font.currentText()
        font = QFont(font_name, self._spn_size.value())
        font.setBold(True)
        item = DraggableText(text, font, self._current_color)
        item.set_stroke(self._chk_stroke.isChecked(), self._stroke_color, self._spn_stroke_w.value())
        item.set_shadow(self._chk_shadow.isChecked())
        item.set_glow(self._chk_glow.isChecked(), self._glow_color)
        item.set_gradient(self._chk_gradient.isChecked(), self._gradient_top, self._gradient_bottom)
        item.set_bg_box(self._chk_bg_box.isChecked(), self._bg_box_color)
        item.setPos(30, 30 + len(self._text_items) * 70)
        self._scene.addItem(item)
        self._text_items.append(item)

    def _clear_texts(self):
        for item in self._text_items:
            self._scene.removeItem(item)
        self._text_items.clear()

    def _choose_color(self):
        c = QColorDialog.getColor(self._current_color, self)
        if c.isValid():
            self._current_color = c

    def _choose_stroke_color(self):
        c = QColorDialog.getColor(self._stroke_color, self)
        if c.isValid():
            self._stroke_color = c

    def _choose_glow_color(self):
        c = QColorDialog.getColor(self._glow_color, self)
        if c.isValid():
            self._glow_color = c

    def _apply_preset(self, idx):
        presets = {
            1: {"font": "SVN-Gilroy Black", "size": 60, "color": QColor(255,255,255),
                "stroke": True, "stroke_c": QColor(0,0,0), "stroke_w": 3,
                "shadow": True, "glow": False, "gradient": False, "bg_box": False},
            2: {"font": "SVN-Gilroy Heavy", "size": 48, "color": QColor(255,255,255),
                "stroke": True, "stroke_c": QColor(200,0,0), "stroke_w": 2,
                "shadow": False, "glow": True, "gradient": False, "bg_box": True},
            3: {"font": "SVN-Gilroy Bold", "size": 56, "color": QColor(255,215,0),
                "stroke": True, "stroke_c": QColor(0,0,0), "stroke_w": 2,
                "shadow": True, "glow": False, "gradient": True, "bg_box": False},
            4: {"font": "Inter", "size": 50, "color": QColor(0,255,255),
                "stroke": True, "stroke_c": QColor(128,0,255), "stroke_w": 2,
                "shadow": False, "glow": True, "gradient": False, "bg_box": False},
            5: {"font": "Inter", "size": 44, "color": QColor(255,255,255),
                "stroke": False, "stroke_c": QColor(0,0,0), "stroke_w": 0,
                "shadow": True, "glow": False, "gradient": False, "bg_box": False},
            6: {"font": "SVN-Gilroy Bold", "size": 52, "color": QColor(255,255,255),
                "stroke": True, "stroke_c": QColor(200,0,0), "stroke_w": 3,
                "shadow": False, "glow": False, "gradient": False, "bg_box": False},
        }
        if idx in presets:
            p = presets[idx]
            self._cmb_font.setCurrentText(p["font"])
            self._spn_size.setValue(p["size"])
            self._current_color = p["color"]
            self._chk_stroke.setChecked(p["stroke"])
            self._stroke_color = p["stroke_c"]
            self._spn_stroke_w.setValue(p["stroke_w"])
            self._chk_shadow.setChecked(p["shadow"])
            self._chk_glow.setChecked(p["glow"])
            self._chk_gradient.setChecked(p["gradient"])
            self._chk_bg_box.setChecked(p["bg_box"])

    def _export(self):
        if not self._selected_frame:
            self._main.set_status("⚠ Chọn frame trước khi export")
            return
        if self._video_path:
            base = os.path.splitext(self._video_path)[0]
            default_path = f"{base}_thumbnail.png"
        else:
            default_path = "thumbnail.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Thumbnail", default_path,
            filter="PNG (*.png);;JPEG (*.jpg)")
        if not path:
            return
        scene_rect = self._scene.sceneRect()
        image = QImage(int(scene_rect.width()), int(scene_rect.height()), QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._scene.render(painter)
        painter.end()
        image.save(path)
        self._main.set_status(f"✅ Thumbnail saved: {path}")
