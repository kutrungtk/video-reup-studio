"""
Video Reup Studio Rebuild — Batch Quick Edit Page
Chỉnh sửa nhanh hàng loạt video: Anti-Reup, MD5, Intro/Outro, Thumbnail, Logo, BGM.
Multi-thread processing via ThreadPoolExecutor.
"""

import os
import random
import string
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame, QFileDialog, QProgressBar,
    QTextEdit, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QAbstractItemView, QGroupBox,
    QSlider, QGridLayout, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QImage


# ============================================================
# Logo Preview Widget — drag to position, see live preview
# ============================================================
class LogoPreviewWidget(QWidget):
    """Preview widget showing video frame + draggable logo overlay."""

    position_changed = Signal(float, float)  # (x_ratio, y_ratio) 0.0-1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        self.setMaximumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: #0d0d0d; border: 1px solid #333; border-radius: 8px;")
        self.setMouseTracking(True)

        self._bg_pixmap = None  # video frame thumbnail
        self._logo_pixmap = None
        self._logo_opacity = 0.8
        self._logo_scale = 0.15  # 15% of preview width

        # Position as ratio (0-1)
        self._logo_x = 0.05  # top-left default
        self._logo_y = 0.05
        self._dragging = False
        self._drag_offset = QPointF(0, 0)

    def set_background(self, path: str):
        """Set background image (video thumbnail)."""
        if path and os.path.isfile(path):
            self._bg_pixmap = QPixmap(path)
        else:
            self._bg_pixmap = None
        self.update()

    def set_logo(self, path: str):
        """Set logo image."""
        if path and os.path.isfile(path):
            self._logo_pixmap = QPixmap(path)
        else:
            self._logo_pixmap = None
        self.update()

    def set_opacity(self, value: float):
        """Set logo opacity 0.0-1.0."""
        self._logo_opacity = max(0.0, min(1.0, value))
        self.update()

    def set_scale(self, value: float):
        """Set logo scale as fraction of preview width."""
        self._logo_scale = max(0.05, min(0.5, value))
        self.update()

    def get_position(self) -> tuple:
        """Return (x_ratio, y_ratio)."""
        return (self._logo_x, self._logo_y)

    def set_position(self, x: float, y: float):
        self._logo_x = x
        self._logo_y = y
        self.update()

    def _logo_rect(self) -> QRectF:
        """Get logo rect in widget coordinates."""
        if not self._logo_pixmap:
            return QRectF()
        w = self.width() * self._logo_scale
        aspect = self._logo_pixmap.height() / max(self._logo_pixmap.width(), 1)
        h = w * aspect
        x = self._logo_x * self.width()
        y = self._logo_y * self.height()
        return QRectF(x, y, w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        if self._bg_pixmap:
            scaled = self._bg_pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.fillRect(self.rect(), QColor("#1a1a2e"))
            painter.setPen(QColor("#555"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Video Preview\n(drop video or select to preview)")

        # Logo overlay
        if self._logo_pixmap:
            rect = self._logo_rect()
            painter.setOpacity(self._logo_opacity)
            painter.drawPixmap(rect.toRect(), self._logo_pixmap.scaled(
                int(rect.width()), int(rect.height()),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
            painter.setOpacity(1.0)

            # Draw border around logo
            painter.setPen(QPen(QColor("#00f2ff"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(rect)

        # Position indicator text
        if self._logo_pixmap:
            painter.setPen(QColor("#00f2ff"))
            pos_text = f"Logo: ({self._logo_x:.0%}, {self._logo_y:.0%})"
            painter.drawText(5, self.height() - 5, pos_text)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._logo_pixmap:
            rect = self._logo_rect()
            if rect.contains(event.position()):
                self._dragging = True
                self._drag_offset = event.position() - rect.topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging and self._logo_pixmap:
            new_x = (event.position().x() - self._drag_offset.x()) / self.width()
            new_y = (event.position().y() - self._drag_offset.y()) / self.height()
            self._logo_x = max(0.0, min(0.85, new_x))
            self._logo_y = max(0.0, min(0.85, new_y))
            self.position_changed.emit(self._logo_x, self._logo_y)
            self.update()

    def mouseReleaseEvent(self, event):
        self._dragging = False


# ============================================================
# Quick Edit Worker — multi-thread ffmpeg processing
# ============================================================
class QuickEditWorker(QThread):
    """Process multiple videos with ffmpeg in parallel."""

    progress = Signal(int, str)  # (row_index, status)
    log = Signal(str)
    all_done = Signal(int, int)  # (success, failed)
    error = Signal(str)  # critical error (e.g. ffmpeg not found)

    def __init__(self, tasks: list, settings: dict, max_workers: int = 4):
        super().__init__()
        self.tasks = tasks  # [{index, input_path, output_path}, ...]
        self.settings = settings
        self.max_workers = max_workers
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import subprocess
        import shutil

        # Find ffmpeg binary
        ffmpeg_bin = None
        from config.constants import PROJECT_ROOT
        for ffmpeg_dir in [
            os.path.join(PROJECT_ROOT, "ffmpeg_bin"),
            os.path.join(PROJECT_ROOT, "src", "engine", "modules", "ffmpeg_bin"),
        ]:
            candidate = os.path.join(ffmpeg_dir, "ffmpeg.exe")
            if os.path.isfile(candidate):
                ffmpeg_bin = candidate
                break
        if not ffmpeg_bin:
            ff = shutil.which("ffmpeg")
            if ff:
                ffmpeg_bin = ff
        if not ffmpeg_bin:
            self.error.emit("❌ Không tìm thấy ffmpeg.exe!\n\n"
                "Cách fix:\n"
                "1. Tải ffmpeg từ https://www.gyan.dev/ffmpeg/builds/\n"
                "2. Copy ffmpeg.exe vào folder ffmpeg_bin/ trong project\n"
                "3. Hoặc cài ffmpeg vào PATH hệ thống")
            return

        success = 0
        failed = 0

        def process_one(task):
            if self._cancelled:
                return False

            idx = task['index']
            input_path = task['input_path']
            # Output filename: YYYY-MM-DD_OriginalName_edited.ext
            from datetime import date
            today = date.today().strftime('%Y-%m-%d')
            orig_name = os.path.splitext(os.path.basename(input_path))[0]
            orig_ext = os.path.splitext(input_path)[1]
            output_path = os.path.join(
                os.path.dirname(task['output_path']),
                f"{today}_{orig_name}_edited{orig_ext}"
            )

            self.progress.emit(idx, "⏳ Processing...")

            try:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                # Build ffmpeg filter chain
                filters = []
                inputs = ["-i", input_path]
                filter_complex_parts = []
                current_stream = "[0:v]"
                input_count = 1

                s = self.settings

                # --- Anti-Reup ---
                if s.get('anti_reup', False):
                    anti_filters = []
                    # Crop first (before rotate to avoid black borders)
                    crop_px = s.get('crop_px', 2)
                    if crop_px > 0:
                        anti_filters.append(f"crop=iw-{crop_px*2}:ih-{crop_px*2}:{crop_px}:{crop_px}")
                    # Rotation (degrees → radians, with bilinear fill)
                    rotation_deg = s.get('rotation_deg', 2)
                    if rotation_deg > 0:
                        angle = rotation_deg * 3.14159 / 180.0
                        anti_filters.append(f"rotate={angle}:fillcolor=none:bilinear=1")
                    # Hue shift
                    hue_shift = s.get('hue_shift', 3)
                    if hue_shift != 0:
                        anti_filters.append(f"hue=h={hue_shift}")
                    # Brightness (small random per file)
                    bright = random.uniform(-0.01, 0.01)
                    anti_filters.append(f"eq=brightness={bright}")
                    # Speed change (setpts must be last video filter)
                    speed_pct = s.get('speed_pct', 100)
                    if speed_pct != 100:
                        speed = speed_pct / 100.0
                        anti_filters.append(f"setpts={1/speed}*PTS")

                    if anti_filters:
                        filter_str = ",".join(anti_filters)
                        filter_complex_parts.append(f"{current_stream}{filter_str}[anti]")
                        current_stream = "[anti]"

                # --- Logo/Watermark ---
                if s.get('logo_enabled', False) and s.get('logo_path') and os.path.isfile(s['logo_path']):
                    inputs += ["-i", s['logo_path']]
                    logo_x = s.get('logo_x', 0.05)
                    logo_y = s.get('logo_y', 0.05)
                    opacity = s.get('logo_opacity', 0.8)
                    scale = s.get('logo_scale', 0.15)

                    # Scale logo relative to video width
                    logo_filter = f"[{input_count}:v]scale=iw*{scale}:-1,format=rgba,colorchannelmixer=aa={opacity}[logo]"
                    filter_complex_parts.append(logo_filter)

                    overlay_x = f"W*{logo_x}"
                    overlay_y = f"H*{logo_y}"
                    filter_complex_parts.append(f"{current_stream}[logo]overlay={overlay_x}:{overlay_y}[logod]")
                    current_stream = "[logod]"
                    input_count += 1

                # --- Intro ---
                intro_path = s.get('intro_path', '')
                has_intro = s.get('intro_enabled', False) and intro_path and os.path.isfile(intro_path)

                # --- Outro ---
                outro_path = s.get('outro_path', '')
                has_outro = s.get('outro_enabled', False) and outro_path and os.path.isfile(outro_path)

                # Build final ffmpeg command
                cmd = [ffmpeg_bin, "-y"]
                cmd += inputs

                if has_intro:
                    cmd += ["-i", intro_path]
                    input_count += 1
                if has_outro:
                    cmd += ["-i", outro_path]
                    input_count += 1

                # Audio tempo if speed changed
                speed_pct = s.get('speed_pct', 100)
                if s.get('anti_reup', False) and speed_pct != 100:
                    speed = speed_pct / 100.0
                    # atempo only accepts 0.5-2.0, chain if needed
                    atempo_val = max(0.5, min(2.0, speed))
                    filter_complex_parts.append(f"[0:a]atempo={atempo_val}[aout]")
                    audio_map = "[aout]"
                else:
                    audio_map = "0:a?"

                # Video encode — platform-aware HD quality
                # Get platform preset
                platform = s.get('platform', 'tiktok')
                from config.constants import get_encode_params
                quality = s.get('quality', 'fullhd')
                preset = get_encode_params(platform, quality)

                # Scale to target resolution (BEFORE building cmd)
                w, h = preset["w"], preset["h"]
                if w > 0:
                    scale_filter = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
                    if filter_complex_parts:
                        filter_complex_parts.append(f"{current_stream}{scale_filter}[scaled]")
                        current_stream = "[scaled]"
                    else:
                        filter_complex_parts.append(f"[0:v]{scale_filter}[scaled]")
                        current_stream = "[scaled]"

                # Force FPS (BEFORE building cmd)
                fps = preset.get("fps", 30)
                if fps > 0:
                    fps_filter = f"fps={fps}"
                    if filter_complex_parts:
                        filter_complex_parts.append(f"{current_stream}{fps_filter}[fpsd]")
                        current_stream = "[fpsd]"
                    else:
                        filter_complex_parts.append(f"[0:v]{fps_filter}[fpsd]")
                        current_stream = "[fpsd]"

                # NOW build filter_complex into cmd
                if filter_complex_parts:
                    filter_complex = ";".join(filter_complex_parts)
                    cmd += ["-filter_complex", filter_complex, "-map", current_stream, "-map", audio_map]
                else:
                    cmd += ["-map", "0:v", "-map", "0:a?"]

                # MD5 change — random metadata
                if s.get('md5_change', False):
                    rand_str = ''.join(random.choices(string.ascii_letters, k=16))
                    cmd += ["-metadata", f"comment={rand_str}"]

                # Encode — GPU auto-detect
                from engine.modules.gpu_detect import get_encode_command
                encode_params = get_encode_command(quality)
                # Override maxrate/bufsize from preset
                final_encode = []
                skip_next = False
                for j, p in enumerate(encode_params):
                    if skip_next:
                        skip_next = False
                        continue
                    if p in ("-maxrate", "-bufsize"):
                        skip_next = True
                        continue
                    final_encode.append(p)
                final_encode += ["-maxrate", preset["maxrate"], "-bufsize", preset["bufsize"]]
                # Set keyframe interval
                final_encode += ["-g", str(fps * 2 if fps > 0 else 60)]
                cmd += final_encode

                # Audio
                cmd += ["-c:a", "aac", "-b:a", preset["audio_br"], "-ar", preset["audio_sr"], "-ac", "2"]

                # Temp output (without intro/outro concat)
                if has_intro or has_outro:
                    temp_path = output_path + ".temp.mp4"
                    cmd += [temp_path]
                else:
                    cmd += [output_path]

                # Run main encode
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, creationflags=creationflags)
                if result.returncode != 0:
                    raise RuntimeError(f"ffmpeg error: {result.stderr[-200:]}")

                # Concat intro + main + outro if needed
                if has_intro or has_outro:
                    concat_list = []
                    if has_intro:
                        concat_list.append(intro_path)
                    concat_list.append(temp_path)
                    if has_outro:
                        concat_list.append(outro_path)

                    # Write concat file
                    concat_file = output_path + ".concat.txt"
                    with open(concat_file, 'w') as f:
                        for p in concat_list:
                            f.write(f"file '{p}'\n")

                    concat_cmd = [
                        ffmpeg_bin, "-y", "-f", "concat", "-safe", "0",
                        "-i", concat_file, "-c", "copy",
                        "-movflags", "+faststart", output_path
                    ]
                    result2 = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=300)

                    # Cleanup temp
                    for tmp in [temp_path, concat_file]:
                        if os.path.isfile(tmp):
                            os.remove(tmp)

                    if result2.returncode != 0:
                        raise RuntimeError(f"concat error: {result2.stderr[-200:]}")

                # --- Background Music ---
                if s.get('bgm_enabled', False) and s.get('bgm_path') and os.path.isfile(s['bgm_path']):
                    bgm_vol = s.get('bgm_volume', 0.1)
                    final_with_bgm = output_path + ".bgm.mp4"
                    bgm_cmd = [
                        ffmpeg_bin, "-y",
                        "-i", output_path,
                        "-i", s['bgm_path'],
                        "-filter_complex",
                        f"[1:a]volume={bgm_vol},aloop=loop=-1:size=2e+09[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]",
                        "-map", "0:v", "-map", "[aout]",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        "-movflags", "+faststart", "-shortest", final_with_bgm
                    ]
                    result3 = subprocess.run(bgm_cmd, capture_output=True, text=True, timeout=300)
                    if result3.returncode == 0:
                        os.replace(final_with_bgm, output_path)
                    elif os.path.isfile(final_with_bgm):
                        os.remove(final_with_bgm)

                self.progress.emit(idx, "✅ Done")
                self.log.emit(f"✅ [{idx+1}] {os.path.basename(input_path)}")
                return True

            except Exception as e:
                self.progress.emit(idx, "❌ Error")
                self.log.emit(f"❌ [{idx+1}] {os.path.basename(task['input_path'])}: {e}")
                return False

        # Multi-thread execution
        self.log.emit(f"🚀 Processing {len(self.tasks)} videos ({self.max_workers} workers)...")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(process_one, t): t for t in self.tasks}
            for future in as_completed(futures):
                if self._cancelled:
                    break
                if future.result():
                    success += 1
                else:
                    failed += 1

        self.all_done.emit(success, failed)


# ============================================================
# Batch Quick Edit Page — Main UI
# ============================================================
class BatchQuickEditPage(QWidget):
    """Batch Quick Edit — anti-reup, MD5, logo, intro/outro, BGM."""

    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._worker = None
        self._videos = []  # [{path, filename}, ...]
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # === LEFT: Video list + controls ===
        left = QVBoxLayout()
        left.setSpacing(10)

        header = QLabel("⚡ Batch Quick Edit — Chỉnh sửa nhanh hàng loạt")
        header.setObjectName("SectionHeader")
        left.addWidget(header)

        # Input row
        input_row = QHBoxLayout()
        btn_folder = QPushButton("📂 Chọn Folder Video")
        btn_folder.setObjectName("PrimaryButton")
        btn_folder.setFixedHeight(38)
        btn_folder.clicked.connect(self._browse_input)
        input_row.addWidget(btn_folder)

        btn_files = QPushButton("📄 Chọn Files")
        btn_files.setObjectName("SecondaryButton")
        btn_files.setFixedHeight(38)
        btn_files.clicked.connect(self._browse_files)
        input_row.addWidget(btn_files)

        self._lbl_input = QLabel("Chưa chọn")
        self._lbl_input.setStyleSheet("color: #888;")
        input_row.addWidget(self._lbl_input, 1)
        left.addLayout(input_row)

        # Video table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["☑", "#", "Filename", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().resizeSection(0, 35)
        self._table.horizontalHeader().resizeSection(1, 35)
        self._table.horizontalHeader().resizeSection(3, 100)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet("alternate-background-color: #1a1a2e;")
        self._table.cellClicked.connect(self._on_cell_clicked)
        left.addWidget(self._table, 1)

        # Action row
        action_row = QHBoxLayout()

        self._btn_select_all = QPushButton("☑ All")
        self._btn_select_all.setObjectName("SecondaryButton")
        self._btn_select_all.setFixedWidth(60)
        self._btn_select_all.clicked.connect(self._toggle_select_all)
        action_row.addWidget(self._btn_select_all)

        self._lbl_count = QLabel("0 videos")
        self._lbl_count.setStyleSheet("color: #888;")
        action_row.addWidget(self._lbl_count)

        action_row.addStretch()

        action_row.addWidget(QLabel("Workers:"))
        self._spn_workers = QSpinBox()
        self._spn_workers.setRange(1, 16)
        self._spn_workers.setValue(4)
        action_row.addWidget(self._spn_workers)

        left.addLayout(action_row)

        # Output dir
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output:"))
        self._txt_output = QLineEdit()
        self._txt_output.setPlaceholderText("Folder lưu video đã edit...")
        # Load saved path from settings
        from config.settings import get_settings
        saved_qe_path = get_settings().get("quick_edit_output_dir", "")
        if saved_qe_path:
            self._txt_output.setText(saved_qe_path)
        out_row.addWidget(self._txt_output, 1)
        btn_out = QPushButton("📂")
        btn_out.setFixedWidth(36)
        btn_out.clicked.connect(self._browse_output)
        out_row.addWidget(btn_out)
        left.addLayout(out_row)

        # Progress
        self._progress = QProgressBar()
        self._progress.setMaximumHeight(14)
        left.addWidget(self._progress)

        # Start/Cancel
        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("🚀 START PROCESSING")
        self._btn_start.setObjectName("PrimaryButton")
        self._btn_start.setMinimumHeight(42)
        self._btn_start.clicked.connect(self._start)
        btn_row.addWidget(self._btn_start)

        self._btn_cancel = QPushButton("⏹ Cancel")
        self._btn_cancel.setObjectName("SecondaryButton")
        self._btn_cancel.setVisible(False)
        self._btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self._btn_cancel)
        left.addLayout(btn_row)

        # Log
        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMaximumHeight(90)
        self._txt_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        left.addWidget(self._txt_log)

        layout.addLayout(left, 3)

        # === RIGHT: Settings panel ===
        right = QVBoxLayout()
        right.setSpacing(8)

        # --- Anti-Reup (configurable) ---
        anti_group = QGroupBox("🔀 Anti-Reup")
        anti_layout = QGridLayout(anti_group)

        self._chk_anti = QCheckBox("Enable Anti-Reup")
        self._chk_anti.setChecked(True)
        anti_layout.addWidget(self._chk_anti, 0, 0, 1, 3)

        anti_layout.addWidget(QLabel("Rotation (°):"), 1, 0)
        self._sld_rotation = QSlider(Qt.Orientation.Horizontal)
        self._sld_rotation.setRange(0, 5)
        self._sld_rotation.setValue(2)
        anti_layout.addWidget(self._sld_rotation, 1, 1)
        self._lbl_rotation = QLabel("2°")
        self._sld_rotation.valueChanged.connect(lambda v: self._lbl_rotation.setText(f"{v}°"))
        anti_layout.addWidget(self._lbl_rotation, 1, 2)

        anti_layout.addWidget(QLabel("Speed (%):"), 2, 0)
        self._sld_speed = QSlider(Qt.Orientation.Horizontal)
        self._sld_speed.setRange(95, 105)
        self._sld_speed.setValue(100)
        anti_layout.addWidget(self._sld_speed, 2, 1)
        self._lbl_speed = QLabel("100%")
        self._sld_speed.valueChanged.connect(lambda v: self._lbl_speed.setText(f"{v}%"))
        anti_layout.addWidget(self._lbl_speed, 2, 2)

        anti_layout.addWidget(QLabel("Crop (px):"), 3, 0)
        self._sld_crop = QSlider(Qt.Orientation.Horizontal)
        self._sld_crop.setRange(0, 10)
        self._sld_crop.setValue(2)
        anti_layout.addWidget(self._sld_crop, 3, 1)
        self._lbl_crop = QLabel("2px")
        self._sld_crop.valueChanged.connect(lambda v: self._lbl_crop.setText(f"{v}px"))
        anti_layout.addWidget(self._lbl_crop, 3, 2)

        anti_layout.addWidget(QLabel("Hue shift:"), 4, 0)
        self._sld_hue = QSlider(Qt.Orientation.Horizontal)
        self._sld_hue.setRange(-10, 10)
        self._sld_hue.setValue(3)
        anti_layout.addWidget(self._sld_hue, 4, 1)
        self._lbl_hue = QLabel("3")
        self._sld_hue.valueChanged.connect(lambda v: self._lbl_hue.setText(str(v)))
        anti_layout.addWidget(self._lbl_hue, 4, 2)

        right.addWidget(anti_group)

        # --- MD5 ---
        self._chk_md5 = QCheckBox("🔑 Đổi MD5 (re-encode + random metadata)")
        self._chk_md5.setChecked(True)
        right.addWidget(self._chk_md5)

        # --- Intro/Outro ---
        intro_group = QGroupBox("🎬 Intro / Outro")
        intro_layout = QGridLayout(intro_group)

        self._chk_intro = QCheckBox("Intro:")
        intro_layout.addWidget(self._chk_intro, 0, 0)
        self._txt_intro = QLineEdit()
        self._txt_intro.setPlaceholderText("intro.mp4")
        intro_layout.addWidget(self._txt_intro, 0, 1)
        btn_intro = QPushButton("📂")
        btn_intro.setFixedWidth(30)
        btn_intro.clicked.connect(lambda: self._pick_file(self._txt_intro, "Video (*.mp4 *.mkv *.avi)"))
        intro_layout.addWidget(btn_intro, 0, 2)

        self._chk_outro = QCheckBox("Outro:")
        intro_layout.addWidget(self._chk_outro, 1, 0)
        self._txt_outro = QLineEdit()
        self._txt_outro.setPlaceholderText("outro.mp4")
        intro_layout.addWidget(self._txt_outro, 1, 1)
        btn_outro = QPushButton("📂")
        btn_outro.setFixedWidth(30)
        btn_outro.clicked.connect(lambda: self._pick_file(self._txt_outro, "Video (*.mp4 *.mkv *.avi)"))
        intro_layout.addWidget(btn_outro, 1, 2)

        right.addWidget(intro_group)

        # --- Logo/Watermark with PREVIEW ---
        logo_group = QGroupBox("🏷️ Logo / Watermark")
        logo_layout = QVBoxLayout(logo_group)

        logo_top = QHBoxLayout()
        self._chk_logo = QCheckBox("Enable")
        self._chk_logo.toggled.connect(self._on_logo_toggled)
        logo_top.addWidget(self._chk_logo)
        self._txt_logo = QLineEdit()
        self._txt_logo.setPlaceholderText("logo.png (transparent)")
        logo_top.addWidget(self._txt_logo, 1)
        btn_logo = QPushButton("📂")
        btn_logo.setFixedWidth(30)
        btn_logo.clicked.connect(self._pick_logo)
        logo_top.addWidget(btn_logo)
        logo_layout.addLayout(logo_top)

        # Preview
        self._logo_preview = LogoPreviewWidget()
        logo_layout.addWidget(self._logo_preview)

        # Opacity + Scale sliders
        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Opacity:"))
        self._sld_opacity = QSlider(Qt.Orientation.Horizontal)
        self._sld_opacity.setRange(10, 100)
        self._sld_opacity.setValue(80)
        self._sld_opacity.valueChanged.connect(lambda v: self._logo_preview.set_opacity(v / 100.0))
        slider_row.addWidget(self._sld_opacity)
        self._lbl_opacity = QLabel("80%")
        self._sld_opacity.valueChanged.connect(lambda v: self._lbl_opacity.setText(f"{v}%"))
        slider_row.addWidget(self._lbl_opacity)

        slider_row.addWidget(QLabel("  Size:"))
        self._sld_scale = QSlider(Qt.Orientation.Horizontal)
        self._sld_scale.setRange(5, 40)
        self._sld_scale.setValue(15)
        self._sld_scale.valueChanged.connect(lambda v: self._logo_preview.set_scale(v / 100.0))
        slider_row.addWidget(self._sld_scale)
        self._lbl_scale = QLabel("15%")
        self._sld_scale.valueChanged.connect(lambda v: self._lbl_scale.setText(f"{v}%"))
        slider_row.addWidget(self._lbl_scale)
        logo_layout.addLayout(slider_row)

        # Quick position buttons
        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("Quick:"))
        for name, x, y in [("↖ TL", 0.02, 0.02), ("↗ TR", 0.82, 0.02), ("↙ BL", 0.02, 0.85), ("↘ BR", 0.82, 0.85), ("⊕ Center", 0.42, 0.42)]:
            btn = QPushButton(name)
            btn.setFixedWidth(52)
            btn.setStyleSheet("font-size: 10px;")
            btn.clicked.connect(lambda checked, px=x, py=y: self._logo_preview.set_position(px, py))
            pos_row.addWidget(btn)
        pos_row.addStretch()
        logo_layout.addLayout(pos_row)

        right.addWidget(logo_group)

        # --- Background Music ---
        bgm_group = QGroupBox("🎵 Background Music")
        bgm_layout = QHBoxLayout(bgm_group)
        self._chk_bgm = QCheckBox("Enable")
        bgm_layout.addWidget(self._chk_bgm)
        self._txt_bgm = QLineEdit()
        self._txt_bgm.setPlaceholderText("music.mp3")
        bgm_layout.addWidget(self._txt_bgm, 1)
        btn_bgm = QPushButton("📂")
        btn_bgm.setFixedWidth(30)
        btn_bgm.clicked.connect(lambda: self._pick_file(self._txt_bgm, "Audio (*.mp3 *.wav *.m4a *.ogg)"))
        bgm_layout.addWidget(btn_bgm)
        bgm_layout.addWidget(QLabel("Vol:"))
        self._spn_bgm_vol = QSpinBox()
        self._spn_bgm_vol.setRange(1, 50)
        self._spn_bgm_vol.setValue(10)
        self._spn_bgm_vol.setSuffix("%")
        bgm_layout.addWidget(self._spn_bgm_vol)
        right.addWidget(bgm_group)

        # === Export Format ===
        export_group = QGroupBox("📤 Export Format")
        export_layout = QGridLayout(export_group)

        export_layout.addWidget(QLabel("Platform:"), 0, 0)
        self._cmb_platform = QComboBox()
        self._cmb_platform.addItem("🎵 TikTok", "tiktok")
        self._cmb_platform.addItem("▶️ YouTube Shorts", "yt_shorts")
        self._cmb_platform.addItem("▶️ YouTube", "youtube")
        self._cmb_platform.addItem("📘 Facebook Reels", "fb_reels")
        self._cmb_platform.addItem("📘 Facebook Feed", "fb_feed")
        self._cmb_platform.addItem("📷 Instagram Reels", "ig_reels")
        self._cmb_platform.currentIndexChanged.connect(self._on_export_changed)
        export_layout.addWidget(self._cmb_platform, 0, 1)

        export_layout.addWidget(QLabel("Chất lượng:"), 0, 2)
        self._cmb_quality = QComboBox()
        self._cmb_quality.addItem("Full HD 1080p", "fullhd")
        self._cmb_quality.addItem("2K 1440p", "2k")
        self._cmb_quality.currentIndexChanged.connect(self._on_export_changed)
        export_layout.addWidget(self._cmb_quality, 0, 3)

        self._lbl_format_info = QLabel("")
        self._lbl_format_info.setStyleSheet("color: #4fc3f7; font-size: 11px;")
        export_layout.addWidget(self._lbl_format_info, 1, 0, 1, 3)

        # GPU status label
        self._lbl_gpu = QLabel("")
        self._lbl_gpu.setStyleSheet("color: #81c784; font-size: 11px;")
        export_layout.addWidget(self._lbl_gpu, 1, 3)

        right.addWidget(export_group)

        right.addStretch()
        layout.addLayout(right, 2)

    # === Platform Presets ===
    # (Platform × Quality tính từ constants.get_encode_params)

    def _on_export_changed(self, index=None):
        """Update info label when platform or quality changes."""
        from config.constants import get_encode_params, PLATFORMS
        platform_key = self._cmb_platform.currentData()
        quality_key = self._cmb_quality.currentData()
        params = get_encode_params(platform_key, quality_key)
        platform = PLATFORMS.get(platform_key, {})
        self._lbl_format_info.setText(
            f"📐 {params['w']}×{params['h']} | {params['aspect']} | {params['fps']}fps | "
            f"CRF {params['crf']} max {params['maxrate']} | AAC {platform.get('audio_br','192k')}/{platform.get('audio_sr','44100')}Hz"
        )
        # Detect GPU (cached, runs once)
        try:
            from engine.modules.gpu_detect import detect_gpu_encoder
            enc = detect_gpu_encoder()
            self._lbl_gpu.setText(f"{enc['icon']} {enc['name']}")
        except Exception:
            self._lbl_gpu.setText("💻 CPU mode")

    # === Actions ===

    def _browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn folder chứa video")
        if folder:
            self._load_videos_from_folder(folder)

    def _browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn video files", filter="Video (*.mp4 *.mkv *.avi *.webm *.mov)")
        if files:
            self._load_video_files(files)

    def _browse_output(self):
        p = QFileDialog.getExistingDirectory(self, "Chọn folder output")
        if p:
            self._txt_output.setText(p)
            # Save path for next session
            from config.settings import get_settings
            get_settings().set("quick_edit_output_dir", p)

    def _pick_file(self, line_edit, filter_str):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file", filter=filter_str)
        if path:
            line_edit.setText(path)

    def _pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn logo", filter="Image (*.png *.jpg *.webp *.bmp)")
        if path:
            self._txt_logo.setText(path)
            self._logo_preview.set_logo(path)

    def _on_logo_toggled(self, checked):
        self._logo_preview.setVisible(checked)

    def _load_videos_from_folder(self, folder):
        exts = {'.mp4', '.mkv', '.avi', '.webm', '.mov', '.flv'}
        files = [os.path.join(folder, f) for f in sorted(os.listdir(folder)) if os.path.splitext(f)[1].lower() in exts]
        self._load_video_files(files)
        self._lbl_input.setText(folder)
        # Auto-set output
        if not self._txt_output.text():
            self._txt_output.setText(os.path.join(folder, "edited"))

    def _load_video_files(self, files):
        self._videos.clear()
        self._table.setRowCount(0)

        for f in files:
            self._videos.append({'path': f, 'filename': os.path.basename(f)})

        for i, v in enumerate(self._videos):
            row = self._table.rowCount()
            self._table.insertRow(row)

            chk = QTableWidgetItem("☑")
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, chk)

            idx = QTableWidgetItem(str(i + 1))
            idx.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, idx)

            self._table.setItem(row, 2, QTableWidgetItem(v['filename']))

            status = QTableWidgetItem("Ready")
            status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 3, status)

        self._lbl_count.setText(f"{len(self._videos)} videos")

        # Set first video as preview background
        if self._videos:
            self._logo_preview.set_background("")  # TODO: extract thumbnail from first video

    def _on_cell_clicked(self, row, col):
        """Toggle checkbox when clicking column 0."""
        if col == 0:
            item = self._table.item(row, 0)
            if item:
                item.setText("☐" if item.text() == "☑" else "☑")

    def _toggle_select_all(self):
        all_checked = all(
            self._table.item(r, 0) and self._table.item(r, 0).text() == "☑"
            for r in range(self._table.rowCount())
        )
        new_state = "☐" if all_checked else "☑"
        for r in range(self._table.rowCount()):
            if self._table.item(r, 0):
                self._table.item(r, 0).setText(new_state)

    def _start(self):
        # Collect selected videos
        tasks = []
        output_dir = self._txt_output.text().strip()
        if not output_dir:
            self._txt_log.append("⚠ Chọn folder output trước")
            return

        for row in range(self._table.rowCount()):
            chk = self._table.item(row, 0)
            if chk and chk.text() == "☑":
                v = self._videos[row]
                out_path = os.path.join(output_dir, v['filename'])
                tasks.append({
                    'index': row,
                    'input_path': v['path'],
                    'output_path': out_path,
                })

        if not tasks:
            self._txt_log.append("⚠ Chọn video trước")
            return

        # Build settings dict
        logo_x, logo_y = self._logo_preview.get_position()
        settings = {
            'anti_reup': self._chk_anti.isChecked(),
            'rotation_deg': self._sld_rotation.value(),
            'speed_pct': self._sld_speed.value(),
            'crop_px': self._sld_crop.value(),
            'hue_shift': self._sld_hue.value(),
            'md5_change': self._chk_md5.isChecked(),
            'intro_enabled': self._chk_intro.isChecked(),
            'intro_path': self._txt_intro.text().strip(),
            'outro_enabled': self._chk_outro.isChecked(),
            'outro_path': self._txt_outro.text().strip(),
            'logo_enabled': self._chk_logo.isChecked(),
            'logo_path': self._txt_logo.text().strip(),
            'logo_x': logo_x,
            'logo_y': logo_y,
            'logo_opacity': self._sld_opacity.value() / 100.0,
            'logo_scale': self._sld_scale.value() / 100.0,
            'bgm_enabled': self._chk_bgm.isChecked(),
            'bgm_path': self._txt_bgm.text().strip(),
            'bgm_volume': self._spn_bgm_vol.value() / 100.0,
            'platform': self._cmb_platform.currentData(),
            'quality': self._cmb_quality.currentData(),
        }

        workers = self._spn_workers.value()

        self._btn_start.setEnabled(False)
        self._btn_start.setText("⏳ Processing...")
        self._btn_cancel.setVisible(True)
        self._progress.setValue(0)
        self._txt_log.clear()

        self._worker = QuickEditWorker(tasks, settings, workers)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(lambda m: self._txt_log.append(m))
        self._worker.all_done.connect(self._on_done)
        self._worker.error.connect(lambda m: (self._txt_log.append(m), self._on_done(0, 0)))
        self._worker.start()

    def _on_progress(self, row, status):
        if row < self._table.rowCount():
            self._table.item(row, 3).setText(status)
        done = sum(1 for r in range(self._table.rowCount())
                   if self._table.item(r, 3) and self._table.item(r, 3).text() in ("✅ Done", "❌ Error"))
        total = self._table.rowCount()
        if total > 0:
            self._progress.setValue(int(done / total * 100))

    def _on_done(self, success, failed):
        self._btn_start.setEnabled(True)
        self._btn_start.setText("🚀 START PROCESSING")
        self._btn_cancel.setVisible(False)
        self._progress.setValue(100)
        self._txt_log.append(f"\n✅ Done! Success: {success}, Failed: {failed}")
        self._txt_log.append(f"📂 Output: {self._txt_output.text()}")

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
            self._txt_log.append("⏹ Cancelling...")
