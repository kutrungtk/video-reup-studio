"""
Export Page — Galaxy Filters + Anti-reup Pro + Split + Encode → final video
INPUT: composed_final.mp4
OUTPUT: final_tiktok_001.mp4, final_tiktok_002.mp4, ...

Features:
- Galaxy Filters: Cinematic, Vintage, B&W, Warm, Cool, Neon, Sepia, Teal&Orange
- Anti-reup Pro: đổi MD5, flip nhẹ, noise, shift pixels, speed tweak, metadata strip
- Split by duration (for Shorts/Reels)
- Platform presets (TikTok, YouTube, Instagram)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QFrame, QFileDialog,
    QProgressBar, QTextEdit, QSpinBox, QDoubleSpinBox, QGridLayout,
    QGroupBox, QSlider, QTabWidget,
)
from PySide6.QtCore import Qt

from config.constants import PLATFORMS


# Galaxy Filter definitions (FFmpeg colorbalance/curves/eq filters)
GALAXY_FILTERS = {
    "none": {"label": "🚫 None (Original)", "filter": ""},
    "cinematic": {"label": "🎬 Cinematic", "filter": "curves=preset=cross_process,eq=contrast=1.1:brightness=0.02:saturation=1.2"},
    "vintage": {"label": "📷 Vintage", "filter": "curves=preset=vintage,eq=saturation=0.8:brightness=0.05"},
    "bw": {"label": "⬛ Black & White", "filter": "hue=s=0,eq=contrast=1.2:brightness=0.03"},
    "warm": {"label": "🔥 Warm", "filter": "colorbalance=rs=0.1:gs=0.05:bs=-0.1,eq=saturation=1.1"},
    "cool": {"label": "❄️ Cool", "filter": "colorbalance=rs=-0.1:gs=0.0:bs=0.15,eq=saturation=1.05"},
    "neon": {"label": "💜 Neon", "filter": "eq=contrast=1.3:brightness=-0.05:saturation=1.8,curves=preset=cross_process"},
    "sepia": {"label": "🟤 Sepia", "filter": "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131,eq=brightness=0.05"},
    "teal_orange": {"label": "🎨 Teal & Orange", "filter": "colorbalance=rs=0.15:gs=-0.05:bs=-0.15:rh=0.1:gh=-0.05:bh=0.1,eq=saturation=1.2"},
    "dark_moody": {"label": "🌑 Dark Moody", "filter": "eq=contrast=1.2:brightness=-0.08:saturation=0.9,curves=preset=darker"},
    "pastel": {"label": "🌸 Pastel", "filter": "eq=brightness=0.1:saturation=0.6:contrast=0.9"},
    "high_contrast": {"label": "⚡ High Contrast", "filter": "eq=contrast=1.5:brightness=-0.02:saturation=1.1"},
}

# Anti-reup techniques
ANTI_REUP_TECHNIQUES = {
    "md5_change": {"label": "🔀 Đổi MD5 (metadata random)", "default": True},
    "speed_tweak": {"label": "⚡ Speed tweak (1.01x-1.03x)", "default": True},
    "pixel_shift": {"label": "📐 Pixel shift (crop 2-4px)", "default": True},
    "flip_slight": {"label": "🔄 Flip nhẹ (mirror 1%)", "default": False},
    "noise": {"label": "🌫️ Thêm noise nhẹ", "default": True},
    "brightness_jitter": {"label": "💡 Brightness jitter (±2%)", "default": True},
    "audio_pitch": {"label": "🎵 Audio pitch shift (±0.5%)", "default": True},
    "strip_metadata": {"label": "🗑️ Strip all metadata", "default": True},
}


class ExportPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        h = QLabel("📤 Export — Galaxy Filters + Anti-reup + Split")
        h.setObjectName("SectionHeader")
        layout.addWidget(h)

        # Tabs: Main Export | Galaxy Filters | Anti-reup Pro
        tabs = QTabWidget()

        # === TAB 1: Main Export ===
        tab_main = QWidget()
        tab_main_layout = QVBoxLayout(tab_main)
        self._build_main_tab(tab_main_layout)
        tabs.addTab(tab_main, "📤 Export")

        # === TAB 2: Galaxy Filters ===
        tab_filters = QWidget()
        tab_filters_layout = QVBoxLayout(tab_filters)
        self._build_filters_tab(tab_filters_layout)
        tabs.addTab(tab_filters, "🎨 Galaxy Filters")

        # === TAB 3: Anti-reup Pro ===
        tab_antireup = QWidget()
        tab_antireup_layout = QVBoxLayout(tab_antireup)
        self._build_antireup_tab(tab_antireup_layout)
        tabs.addTab(tab_antireup, "🛡️ Anti-reup Pro")

        layout.addWidget(tabs, 1)

        # Progress + Log (shared)
        self._progress = QProgressBar()
        layout.addWidget(self._progress)

        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMaximumHeight(120)
        self._txt_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        layout.addWidget(self._txt_log)

    def _build_main_tab(self, layout):
        """Main export settings."""
        # Input/Output
        row1 = QHBoxLayout()
        lbl_in = QLabel("Input:")
        lbl_in.setFixedWidth(55)
        row1.addWidget(lbl_in)
        self._txt_input = QLineEdit()
        self._txt_input.setPlaceholderText("Chọn video cần export...")
        row1.addWidget(self._txt_input)
        btn1 = QPushButton("📂 Chọn Video")
        btn1.setObjectName("SecondaryButton")
        btn1.setFixedWidth(100)
        btn1.clicked.connect(lambda: self._browse(self._txt_input))
        row1.addWidget(btn1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        lbl_out = QLabel("Output:")
        lbl_out.setFixedWidth(55)
        row2.addWidget(lbl_out)
        self._txt_output = QLineEdit()
        self._txt_output.setPlaceholderText("Folder lưu video export...")
        # Load saved path
        from config.settings import get_settings
        saved_path = get_settings().get("export_output_dir", "")
        if saved_path:
            self._txt_output.setText(saved_path)
        row2.addWidget(self._txt_output)
        btn2 = QPushButton("📂 Chọn Folder")
        btn2.setObjectName("SecondaryButton")
        btn2.setFixedWidth(100)
        btn2.clicked.connect(lambda: self._browse_dir(self._txt_output))
        row2.addWidget(btn2)
        layout.addLayout(row2)

        # === Platform + Quality Selection ===
        platform_group = QGroupBox("📤 Platform Export")
        pg_layout = QGridLayout(platform_group)

        pg_layout.addWidget(QLabel("Platform:"), 0, 0)
        self._cmb_platform = QComboBox()
        self._cmb_platform.addItem("🎵 TikTok", "tiktok")
        self._cmb_platform.addItem("▶️ YouTube Shorts", "yt_shorts")
        self._cmb_platform.addItem("▶️ YouTube", "youtube")
        self._cmb_platform.addItem("📘 Facebook Reels", "fb_reels")
        self._cmb_platform.addItem("📘 Facebook Feed", "fb_feed")
        self._cmb_platform.addItem("📷 Instagram Reels", "ig_reels")
        self._cmb_platform.currentIndexChanged.connect(self._on_platform)
        pg_layout.addWidget(self._cmb_platform, 0, 1)

        pg_layout.addWidget(QLabel("Chất lượng:"), 0, 2)
        self._cmb_quality = QComboBox()
        self._cmb_quality.addItem("Full HD 1080p", "fullhd")
        self._cmb_quality.addItem("2K 1440p", "2k")
        self._cmb_quality.currentIndexChanged.connect(self._on_platform)
        pg_layout.addWidget(self._cmb_quality, 0, 3)

        # Info label
        self._lbl_platform_info = QLabel("")
        self._lbl_platform_info.setStyleSheet("color: #4fc3f7; font-size: 11px; padding: 4px;")
        self._lbl_platform_info.setWordWrap(True)
        pg_layout.addWidget(self._lbl_platform_info, 1, 0, 1, 3)

        # GPU status
        self._lbl_gpu = QLabel("")
        self._lbl_gpu.setStyleSheet("color: #81c784; font-size: 11px;")
        pg_layout.addWidget(self._lbl_gpu, 1, 3)

        layout.addWidget(platform_group)

        # === Options ===
        opts_group = QGroupBox("⚙️ Options")
        opts_layout = QGridLayout(opts_group)

        opts_layout.addWidget(QLabel("Speed:"), 0, 0)
        self._spn_speed = QDoubleSpinBox()
        self._spn_speed.setRange(0.5, 3.0)
        self._spn_speed.setValue(1.0)
        self._spn_speed.setSingleStep(0.05)
        self._spn_speed.setSuffix("x")
        opts_layout.addWidget(self._spn_speed, 0, 1)

        self._chk_split = QCheckBox("Split by duration")
        self._chk_split.setChecked(False)
        opts_layout.addWidget(self._chk_split, 0, 2)

        self._spn_dur = QSpinBox()
        self._spn_dur.setRange(10, 3600)
        self._spn_dur.setValue(60)
        self._spn_dur.setSuffix("s")
        opts_layout.addWidget(self._spn_dur, 0, 3)

        self._chk_ar = QCheckBox("🛡️ Anti-reup Pro")
        self._chk_ar.setChecked(True)
        opts_layout.addWidget(self._chk_ar, 1, 0, 1, 2)

        layout.addWidget(opts_group)

        # Export button
        self._btn = QPushButton("📤 EXPORT")
        self._btn.setObjectName("PrimaryButton")
        self._btn.setMinimumHeight(44)
        self._btn.setStyleSheet("""
            QPushButton { font-size: 15px; font-weight: bold; background: #1ed760; color: #000; border-radius: 8px; }
            QPushButton:hover { background: #1db954; }
            QPushButton:disabled { background: #333; color: #666; }
        """)
        self._btn.clicked.connect(self._export)
        layout.addWidget(self._btn)

        layout.addStretch()

        # Trigger initial platform info
        self._on_platform(0)

    def _build_filters_tab(self, layout):
        """Galaxy Filters — color grading presets."""
        desc = QLabel("Phủ màu điện ảnh lên video — chọn filter rồi bấm Export ở tab chính")
        desc.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(desc)

        # Filter grid (2 columns)
        grid = QGridLayout()
        self._filter_buttons = {}
        self._selected_filter = "none"

        row, col = 0, 0
        for key, info in GALAXY_FILTERS.items():
            btn = QPushButton(info["label"])
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { padding: 10px 16px; border: 1px solid #333; border-radius: 6px; font-size: 12px; }
                QPushButton:checked { border: 2px solid #1ed760; background: #1a2e1a; }
                QPushButton:hover { border-color: #555; }
            """)
            btn.clicked.connect(lambda checked, k=key: self._select_filter(k))
            if key == "none":
                btn.setChecked(True)
            grid.addWidget(btn, row, col)
            self._filter_buttons[key] = btn
            col += 1
            if col >= 3:
                col = 0
                row += 1

        layout.addLayout(grid)

        # Filter intensity slider
        intensity_row = QHBoxLayout()
        intensity_row.addWidget(QLabel("Intensity:"))
        self._slider_intensity = QSlider(Qt.Orientation.Horizontal)
        self._slider_intensity.setRange(20, 100)
        self._slider_intensity.setValue(100)
        intensity_row.addWidget(self._slider_intensity)
        self._lbl_intensity = QLabel("100%")
        self._slider_intensity.valueChanged.connect(lambda v: self._lbl_intensity.setText(f"{v}%"))
        intensity_row.addWidget(self._lbl_intensity)
        layout.addLayout(intensity_row)

        layout.addStretch()

    def _build_antireup_tab(self, layout):
        """Anti-reup Pro — multiple techniques to avoid copyright detection."""
        desc = QLabel("Kỹ thuật chống phát hiện bản quyền — tick chọn các phương pháp muốn áp dụng")
        desc.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(desc)

        # Technique checkboxes
        self._antireup_checks = {}
        for key, info in ANTI_REUP_TECHNIQUES.items():
            chk = QCheckBox(info["label"])
            chk.setChecked(info["default"])
            chk.setStyleSheet("font-size: 12px; padding: 4px;")
            layout.addWidget(chk)
            self._antireup_checks[key] = chk

        # Custom settings
        custom_group = QGroupBox("Tùy chỉnh")
        cg_layout = QGridLayout(custom_group)

        cg_layout.addWidget(QLabel("Speed range:"), 0, 0)
        self._spn_speed_min = QDoubleSpinBox()
        self._spn_speed_min.setRange(1.0, 1.1)
        self._spn_speed_min.setValue(1.01)
        self._spn_speed_min.setSingleStep(0.005)
        cg_layout.addWidget(self._spn_speed_min, 0, 1)
        cg_layout.addWidget(QLabel("→"), 0, 2)
        self._spn_speed_max = QDoubleSpinBox()
        self._spn_speed_max.setRange(1.0, 1.1)
        self._spn_speed_max.setValue(1.03)
        self._spn_speed_max.setSingleStep(0.005)
        cg_layout.addWidget(self._spn_speed_max, 0, 3)

        cg_layout.addWidget(QLabel("Pixel crop:"), 1, 0)
        self._spn_crop = QSpinBox()
        self._spn_crop.setRange(1, 10)
        self._spn_crop.setValue(2)
        self._spn_crop.setSuffix("px")
        cg_layout.addWidget(self._spn_crop, 1, 1)

        cg_layout.addWidget(QLabel("Noise level:"), 1, 2)
        self._spn_noise = QSpinBox()
        self._spn_noise.setRange(1, 20)
        self._spn_noise.setValue(3)
        cg_layout.addWidget(self._spn_noise, 1, 3)

        layout.addWidget(custom_group)
        layout.addStretch()

    # === Actions ===

    def _select_filter(self, key):
        self._selected_filter = key
        for k, btn in self._filter_buttons.items():
            btn.setChecked(k == key)

    def _on_platform(self, idx=None):
        from config.constants import get_encode_params, PLATFORMS
        platform_key = self._cmb_platform.currentData()
        quality_key = self._cmb_quality.currentData()
        params = get_encode_params(platform_key, quality_key)
        platform = PLATFORMS.get(platform_key, {})
        self._spn_dur.setValue(platform.get("max_duration", 60))
        self._lbl_platform_info.setText(
            f"📐 {params['w']}×{params['h']} | {params['aspect']} | {params['fps']}fps | "
            f"CRF {params['crf']} max {params['maxrate']} | "
            f"AAC {platform.get('audio_br','192k')}/{platform.get('audio_sr','44100')}Hz"
        )
        # GPU detect (cached)
        try:
            from engine.modules.gpu_detect import detect_gpu_encoder
            enc = detect_gpu_encoder()
            self._lbl_gpu.setText(f"{enc['icon']} {enc['name']}")
        except Exception:
            self._lbl_gpu.setText("💻 CPU mode")

    def _export(self):
        inp = self._txt_input.text().strip()
        out = self._txt_output.text().strip()
        if not inp:
            self._txt_log.append("⚠ Select input video")
            return
        if not out:
            import os
            out = os.path.join(os.path.dirname(inp), "output")
            self._txt_output.setText(out)

        # Build filter string
        filter_key = self._selected_filter
        filter_str = GALAXY_FILTERS.get(filter_key, {}).get("filter", "")
        intensity = self._slider_intensity.value() / 100.0

        # Build anti-reup config
        antireup_techniques = []
        if self._chk_ar.isChecked():
            for key, chk in self._antireup_checks.items():
                if chk.isChecked():
                    antireup_techniques.append(key)

        # Get encode params from Platform × Quality
        from config.constants import get_encode_params
        platform_code = self._cmb_platform.currentData()
        quality_code = self._cmb_quality.currentData()
        params = get_encode_params(platform_code, quality_code)

        # Save output path
        from config.settings import get_settings
        get_settings().set("export_output_dir", out)

        config = {
            "input_path": inp,
            "output_dir": out,
            "platform": platform_code,
            "quality": quality_code,
            "resolution": params["resolution"],
            "split_enabled": self._chk_split.isChecked(),
            "split_duration": self._spn_dur.value(),
            "crf": params["crf"],
            "maxrate": params["maxrate"],
            "bufsize": params["bufsize"],
            "fps": params["fps"],
            "level": params["level"],
            "audio_br": params["audio_br"],
            "audio_sr": params["audio_sr"],
            "speed": self._spn_speed.value(),
            # Galaxy Filter
            "filter": filter_str,
            "filter_name": filter_key,
            "filter_intensity": intensity,
            # Anti-reup Pro
            "anti_reup_enabled": self._chk_ar.isChecked(),
            "anti_reup_techniques": antireup_techniques,
            "speed_range": (self._spn_speed_min.value(), self._spn_speed_max.value()),
            "pixel_crop": self._spn_crop.value(),
            "noise_level": self._spn_noise.value(),
        }

        self._btn.setEnabled(False)
        self._btn.setText("⏳ Exporting...")
        self._progress.setValue(0)
        self._txt_log.clear()
        self._txt_log.append(f"🎬 Exporting: {inp}")
        if filter_str:
            self._txt_log.append(f"🎨 Filter: {GALAXY_FILTERS[filter_key]['label']}")
        if antireup_techniques:
            self._txt_log.append(f"🛡️ Anti-reup: {len(antireup_techniques)} techniques")

        from workers.export_worker import ExportWorker
        self._worker = ExportWorker(config)
        self._worker.progress.connect(lambda p, m: self._progress.setValue(p))
        self._worker.log_message.connect(lambda m: self._txt_log.append(m))
        self._worker.finished.connect(self._done)
        self._worker.error.connect(self._err)
        self._worker.start()

    def _done(self, outputs):
        self._btn.setEnabled(True)
        self._btn.setText("📤 EXPORT")
        self._progress.setValue(100)
        if isinstance(outputs, list):
            self._txt_log.append(f"\n✅ {len(outputs)} files exported!")
        else:
            self._txt_log.append(f"\n✅ Export done: {outputs}")

    def _err(self, msg):
        self._btn.setEnabled(True)
        self._btn.setText("📤 EXPORT")
        self._txt_log.append(f"\n❌ {msg}")

    def _browse(self, txt):
        p, _ = QFileDialog.getOpenFileName(self, "Select video", filter="Video (*.mp4 *.mkv);;All (*)")
        if p: txt.setText(p)

    def _browse_dir(self, txt):
        p = QFileDialog.getExistingDirectory(self, "Select folder")
        if p: txt.setText(p)
