"""
Video Reup Studio Rebuild — Settings Page (Full)
Configure LLM, Image Gen, TTS, paths, pipeline, and preferences.
Learned from NAVTools settings_dialog.py — comprehensive config.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame, QGridLayout, QFileDialog,
    QMessageBox, QCheckBox, QSpinBox, QTabWidget, QScrollArea,
    QDoubleSpinBox, QGroupBox,
)
from PySide6.QtCore import Qt

from config.settings import get_settings


class SettingsPage(QWidget):
    """Settings page — full configuration for all services."""

    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QLabel("⚙ Settings")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        # Tab widget for organized settings
        tabs = QTabWidget()
        tabs.addTab(self._create_llm_tab(), "🤖 LLM / AI")
        tabs.addTab(self._create_tts_tab(), "🎙 Voice / TTS")
        tabs.addTab(self._create_pipeline_tab(), "⚡ Pipeline")
        tabs.addTab(self._create_paths_tab(), "📁 Paths")
        tabs.addTab(self._create_advanced_tab(), "🔧 Advanced")
        layout.addWidget(tabs, 1)

        # Save button
        btn_row = QHBoxLayout()
        btn_save = QPushButton("💾 Save All Settings")
        btn_save.setObjectName("PrimaryButton")
        btn_save.setMinimumHeight(36)
        btn_save.clicked.connect(self._save_settings)
        btn_row.addWidget(btn_save)

        btn_reset = QPushButton("↩ Reset to Defaults")
        btn_reset.setObjectName("SecondaryButton")
        btn_reset.clicked.connect(self._reset_defaults)
        btn_row.addWidget(btn_reset)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    # === TAB 1: LLM / AI ===
    def _create_llm_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)

        # API Endpoint
        group1 = QGroupBox("LLM API (9router)")
        g1_layout = QGridLayout(group1)

        g1_layout.addWidget(QLabel("API Endpoint:"), 0, 0)
        self._txt_llm_endpoint = QLineEdit()
        self._txt_llm_endpoint.setPlaceholderText("http://localhost:20128/v1")
        g1_layout.addWidget(self._txt_llm_endpoint, 0, 1, 1, 2)

        g1_layout.addWidget(QLabel("API Key:"), 1, 0)
        self._txt_api_key = QLineEdit()
        self._txt_api_key.setPlaceholderText("(optional — leave empty for local)")
        self._txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        g1_layout.addWidget(self._txt_api_key, 1, 1)
        btn_show = QPushButton("👁")
        btn_show.setFixedWidth(32)
        btn_show.clicked.connect(lambda: self._txt_api_key.setEchoMode(
            QLineEdit.EchoMode.Normal if self._txt_api_key.echoMode() == QLineEdit.EchoMode.Password
            else QLineEdit.EchoMode.Password))
        g1_layout.addWidget(btn_show, 1, 2)

        g1_layout.addWidget(QLabel("Text Model (rewrite/translate):"), 2, 0)
        self._txt_llm_model = QLineEdit()
        self._txt_llm_model.setPlaceholderText("auto (let 9router decide)")
        g1_layout.addWidget(self._txt_llm_model, 2, 1, 1, 2)

        g1_layout.addWidget(QLabel("Temperature:"), 3, 0)
        self._spn_temperature = QDoubleSpinBox()
        self._spn_temperature.setRange(0.0, 2.0)
        self._spn_temperature.setSingleStep(0.1)
        self._spn_temperature.setValue(0.3)
        g1_layout.addWidget(self._spn_temperature, 3, 1)

        g1_layout.addWidget(QLabel("Max Tokens:"), 4, 0)
        self._spn_max_tokens = QSpinBox()
        self._spn_max_tokens.setRange(256, 16384)
        self._spn_max_tokens.setValue(4096)
        self._spn_max_tokens.setSingleStep(256)
        g1_layout.addWidget(self._spn_max_tokens, 4, 1)

        layout.addWidget(group1)

        # Image Generation
        group2 = QGroupBox("Image Generation (AI Visuals)")
        g2_layout = QGridLayout(group2)

        g2_layout.addWidget(QLabel("Image API Endpoint:"), 0, 0)
        self._txt_image_endpoint = QLineEdit()
        self._txt_image_endpoint.setPlaceholderText("http://localhost:20128/v1")
        g2_layout.addWidget(self._txt_image_endpoint, 0, 1)

        g2_layout.addWidget(QLabel("Image API Key:"), 1, 0)
        self._txt_image_api_key = QLineEdit()
        self._txt_image_api_key.setPlaceholderText("sk-... (key riêng cho image, hoặc dùng chung với LLM)")
        self._txt_image_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        g2_layout.addWidget(self._txt_image_api_key, 1, 1)

        g2_layout.addWidget(QLabel("Image Model:"), 2, 0)
        self._cmb_image_model = QComboBox()
        self._cmb_image_model.setEditable(True)
        self._cmb_image_model.addItems([
            "cx/gpt-5.5-image",
            "dall-e-3",
            "stable-diffusion-xl",
            "flux-1-schnell",
            "imagen-3",
        ])
        g2_layout.addWidget(self._cmb_image_model, 2, 1)

        g2_layout.addWidget(QLabel("Default Resolution:"), 3, 0)
        self._cmb_image_resolution = QComboBox()
        self._cmb_image_resolution.addItems([
            "1080x1920 (Portrait/TikTok)",
            "1920x1080 (Landscape/YouTube)",
            "1080x1080 (Square/Facebook)",
            "512x512 (Fast preview)",
        ])
        g2_layout.addWidget(self._cmb_image_resolution, 3, 1)

        g2_layout.addWidget(QLabel("Image Style Prompt Prefix:"), 4, 0)
        self._txt_style_prefix = QLineEdit()
        self._txt_style_prefix.setPlaceholderText("cinematic, dramatic lighting, 4k, ultra HD")
        g2_layout.addWidget(self._txt_style_prefix, 4, 1)

        layout.addWidget(group2)

        # Gemini (optional)
        group3 = QGroupBox("Gemini API (optional — for vision/analysis)")
        g3_layout = QGridLayout(group3)

        g3_layout.addWidget(QLabel("Gemini API Key:"), 0, 0)
        self._txt_gemini_key = QLineEdit()
        self._txt_gemini_key.setPlaceholderText("(optional — for image analysis, scene detection)")
        self._txt_gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        g3_layout.addWidget(self._txt_gemini_key, 0, 1)

        g3_layout.addWidget(QLabel("Gemini Model:"), 1, 0)
        self._cmb_gemini_model = QComboBox()
        self._cmb_gemini_model.setEditable(True)
        self._cmb_gemini_model.addItems([
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
        ])
        g3_layout.addWidget(self._cmb_gemini_model, 1, 1)

        # Google Login button (lấy session token cho ImageFX)
        g3_layout.addWidget(QLabel("Session Token:"), 2, 0)
        self._txt_session = QLineEdit()
        self._txt_session.setPlaceholderText("ya29.* (auto-filled after login)")
        self._txt_session.setEchoMode(QLineEdit.EchoMode.Password)
        g3_layout.addWidget(self._txt_session, 2, 1)

        login_row = QHBoxLayout()
        btn_login = QPushButton("🔑 Login Google (lấy token)")
        btn_login.setObjectName("PrimaryButton")
        btn_login.clicked.connect(self._login_google)
        login_row.addWidget(btn_login)

        btn_check = QPushButton("✓ Check")
        btn_check.setObjectName("SecondaryButton")
        btn_check.clicked.connect(self._check_session)
        login_row.addWidget(btn_check)

        self._lbl_session_status = QLabel("")
        self._lbl_session_status.setStyleSheet("font-size: 11px;")
        login_row.addWidget(self._lbl_session_status)
        login_row.addStretch()
        g3_layout.addLayout(login_row, 3, 0, 1, 2)

        layout.addWidget(group3)
        layout.addStretch()
        return tab

    # === TAB 2: Voice / TTS ===
    def _create_tts_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)

        group1 = QGroupBox("Voice Engine")
        g1_layout = QGridLayout(group1)

        g1_layout.addWidget(QLabel("Default Engine:"), 0, 0)
        self._cmb_voice_engine = QComboBox()
        self._cmb_voice_engine.addItem("OmniVoice (CUDA — high quality)", "omnivoice")
        self._cmb_voice_engine.addItem("Edge-TTS (Free — fast)", "edge-tts")
        g1_layout.addWidget(self._cmb_voice_engine, 0, 1)

        g1_layout.addWidget(QLabel("OmniVoice URL:"), 1, 0)
        self._txt_omnivoice_url = QLineEdit()
        self._txt_omnivoice_url.setPlaceholderText("http://localhost:8100/tts")
        g1_layout.addWidget(self._txt_omnivoice_url, 1, 1)

        g1_layout.addWidget(QLabel("Default Voice (Edge-TTS):"), 2, 0)
        self._cmb_default_voice = QComboBox()
        self._cmb_default_voice.setEditable(True)
        self._cmb_default_voice.addItems([
            "it-IT-DiegoNeural",
            "it-IT-IsabellaNeural",
            "en-US-GuyNeural",
            "en-US-JennyNeural",
            "en-GB-RyanNeural",
            "vi-VN-NamMinhNeural",
            "vi-VN-HoaiMyNeural",
            "zh-CN-YunxiNeural",
            "ko-KR-InJoonNeural",
            "ja-JP-KeitaNeural",
        ])
        g1_layout.addWidget(self._cmb_default_voice, 2, 1)

        g1_layout.addWidget(QLabel("Voice Speed:"), 3, 0)
        self._txt_voice_speed = QLineEdit()
        self._txt_voice_speed.setPlaceholderText("+0% (e.g. +10%, -5%)")
        g1_layout.addWidget(self._txt_voice_speed, 3, 1)

        layout.addWidget(group1)

        # Whisper
        group2 = QGroupBox("Whisper (Transcription)")
        g2_layout = QGridLayout(group2)

        g2_layout.addWidget(QLabel("Model:"), 0, 0)
        self._cmb_whisper = QComboBox()
        self._cmb_whisper.addItems(["large-v3", "large-v2", "medium", "small", "base", "tiny"])
        g2_layout.addWidget(self._cmb_whisper, 0, 1)

        g2_layout.addWidget(QLabel("Device:"), 1, 0)
        self._cmb_device = QComboBox()
        self._cmb_device.addItems(["cuda", "cpu"])
        g2_layout.addWidget(self._cmb_device, 1, 1)

        g2_layout.addWidget(QLabel("Language (source):"), 2, 0)
        self._cmb_source_lang = QComboBox()
        self._cmb_source_lang.addItem("Auto-detect", "")
        from config.constants import LANGUAGES
        for code, name in LANGUAGES.items():
            self._cmb_source_lang.addItem(f"{name} ({code})", code)
        g2_layout.addWidget(self._cmb_source_lang, 2, 1)

        layout.addWidget(group2)
        layout.addStretch()
        return tab

    # === TAB 3: Pipeline ===
    def _create_pipeline_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)

        group1 = QGroupBox("Pipeline Defaults")
        g1_layout = QGridLayout(group1)

        g1_layout.addWidget(QLabel("Target Language:"), 0, 0)
        self._cmb_target_lang = QComboBox()
        from config.constants import LANGUAGES
        for code, name in LANGUAGES.items():
            self._cmb_target_lang.addItem(f"{name} ({code})", code)
        g1_layout.addWidget(self._cmb_target_lang, 0, 1)

        g1_layout.addWidget(QLabel("Target Duration (s):"), 1, 0)
        self._spn_target_dur = QSpinBox()
        self._spn_target_dur.setRange(15, 600)
        self._spn_target_dur.setValue(60)
        self._spn_target_dur.setSuffix("s")
        self._spn_target_dur.setToolTip("Rewrite sub sẽ rút gọn nội dung cho vừa thời lượng này")
        g1_layout.addWidget(self._spn_target_dur, 1, 1)

        g1_layout.addWidget(QLabel("Platform:"), 2, 0)
        self._cmb_platform = QComboBox()
        from config.constants import PLATFORMS
        for code, info in PLATFORMS.items():
            self._cmb_platform.addItem(f"{info['label']} ({info.get('aspect', '9:16')}, {info['max_duration']}s)", code)
        g1_layout.addWidget(self._cmb_platform, 2, 1)

        g1_layout.addWidget(QLabel("Anti-Reup Preset:"), 3, 0)
        self._cmb_antireup = QComboBox()
        from config.constants import ANTI_REUP_PRESETS
        for p in ANTI_REUP_PRESETS:
            self._cmb_antireup.addItem(p.capitalize(), p)
        self._cmb_antireup.setCurrentIndex(1)
        g1_layout.addWidget(self._cmb_antireup, 2, 1)

        g1_layout.addWidget(QLabel("Mismatch Strategy:"), 3, 0)
        self._cmb_mismatch = QComboBox()
        self._cmb_mismatch.addItems(["freeze_last", "slow_video", "trim_voice"])
        g1_layout.addWidget(self._cmb_mismatch, 3, 1)

        g1_layout.addWidget(QLabel("Transition:"), 4, 0)
        self._cmb_transition = QComboBox()
        self._cmb_transition.addItems(["none", "crossfade", "fade_black", "fade_white"])
        g1_layout.addWidget(self._cmb_transition, 4, 1)

        g1_layout.addWidget(QLabel("Segment Crop %:"), 5, 0)
        self._spn_crop = QDoubleSpinBox()
        self._spn_crop.setRange(0.0, 10.0)
        self._spn_crop.setSingleStep(0.5)
        self._spn_crop.setValue(3.0)
        g1_layout.addWidget(self._spn_crop, 5, 1)

        layout.addWidget(group1)

        group2 = QGroupBox("Task Management")
        g2_layout = QGridLayout(group2)

        g2_layout.addWidget(QLabel("Max Concurrent Tasks:"), 0, 0)
        self._spn_concurrent = QSpinBox()
        self._spn_concurrent.setRange(1, 10)
        self._spn_concurrent.setValue(3)
        g2_layout.addWidget(self._spn_concurrent, 0, 1)

        g2_layout.addWidget(QLabel("Max Retries on Error:"), 1, 0)
        self._spn_retries = QSpinBox()
        self._spn_retries.setRange(0, 10)
        self._spn_retries.setValue(3)
        g2_layout.addWidget(self._spn_retries, 1, 1)

        self._chk_auto_retry = QCheckBox("Auto-retry on transient errors")
        self._chk_auto_retry.setChecked(True)
        g2_layout.addWidget(self._chk_auto_retry, 2, 0, 1, 2)

        self._chk_auto_timeline = QCheckBox("Auto-populate timeline after pipeline")
        self._chk_auto_timeline.setChecked(True)
        g2_layout.addWidget(self._chk_auto_timeline, 3, 0, 1, 2)

        layout.addWidget(group2)
        layout.addStretch()
        return tab

    # === TAB 4: Paths ===
    def _create_paths_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)

        group = QGroupBox("File Paths")
        g_layout = QGridLayout(group)

        paths = [
            ("Workspace:", "_txt_workspace", "E:\\Aiagent\\Projects\\video-reup-studio-rebuild\\workspace"),
            ("Cookies File:", "_txt_cookies", "cookies.txt for yt-dlp"),
            ("FFmpeg Bin:", "_txt_ffmpeg", "ffmpeg_bin/ folder"),
            ("Image Output:", "_txt_img_output", "Default folder for AI images"),
            ("Video Output:", "_txt_vid_output", "Default folder for exported videos"),
        ]

        for i, (label, attr, placeholder) in enumerate(paths):
            g_layout.addWidget(QLabel(label), i, 0)
            txt = QLineEdit()
            txt.setPlaceholderText(placeholder)
            setattr(self, attr, txt)
            g_layout.addWidget(txt, i, 1)
            btn = QPushButton("...")
            btn.setFixedWidth(32)
            btn.clicked.connect(lambda checked, t=txt: self._browse_path(t))
            g_layout.addWidget(btn, i, 2)

        layout.addWidget(group)
        layout.addStretch()
        return tab

    # === TAB 5: Advanced ===
    def _create_advanced_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)

        group = QGroupBox("Advanced Options")
        g_layout = QVBoxLayout(group)

        self._chk_cache_pipeline = QCheckBox("Cache pipeline intermediate results (resume on restart)")
        self._chk_cache_pipeline.setChecked(True)
        g_layout.addWidget(self._chk_cache_pipeline)

        self._chk_sanitize = QCheckBox("Content sanitization (remove celebrity names, violent words)")
        self._chk_sanitize.setChecked(True)
        g_layout.addWidget(self._chk_sanitize)

        self._chk_scene_detect = QCheckBox("Scene detection before cutting (avoid mid-transition cuts)")
        self._chk_scene_detect.setChecked(False)
        g_layout.addWidget(self._chk_scene_detect)

        self._chk_keep_temp = QCheckBox("Keep temporary files after export (for debugging)")
        self._chk_keep_temp.setChecked(False)
        g_layout.addWidget(self._chk_keep_temp)

        row = QHBoxLayout()
        row.addWidget(QLabel("Log retention (days):"))
        self._spn_log_days = QSpinBox()
        self._spn_log_days.setRange(1, 365)
        self._spn_log_days.setValue(30)
        row.addWidget(self._spn_log_days)
        row.addStretch()
        g_layout.addLayout(row)

        layout.addWidget(group)

        # About
        about = QGroupBox("About")
        about_layout = QVBoxLayout(about)
        about_layout.addWidget(QLabel("Video Reup Studio v3.0.0"))
        about_layout.addWidget(QLabel("PySide6 Rebuild — Python + FFmpeg + AI"))
        about_layout.addWidget(QLabel("Engine: OmniVoice, Edge-TTS, WhisperX, 9router LLM"))
        layout.addWidget(about)

        layout.addStretch()
        return tab

    # === Load / Save ===

    def _load_settings(self):
        s = get_settings()
        self._txt_llm_endpoint.setText(s.get("llm_endpoint"))
        self._txt_api_key.setText(s.get("api_key"))
        self._txt_llm_model.setText(s.get("llm_model"))
        self._spn_temperature.setValue(s.get_float("llm_temperature") or 0.3)
        self._spn_max_tokens.setValue(s.get_int("llm_max_tokens") or 4096)
        self._txt_image_endpoint.setText(s.get("image_endpoint"))
        self._txt_image_api_key.setText(s.get("image_api_key"))
        self._cmb_image_model.setCurrentText(s.get("image_model") or "cx/gpt-5.5-image")
        self._txt_style_prefix.setText(s.get("image_style_prefix"))
        self._txt_gemini_key.setText(s.get("gemini_api_key"))
        self._txt_session.setText(s.get("gemini_session_token"))
        self._txt_omnivoice_url.setText(s.get("omnivoice_url") or "http://localhost:8100/tts")
        self._cmb_default_voice.setCurrentText(s.get("edge_tts_voice") or "it-IT-DiegoNeural")
        self._txt_voice_speed.setText(s.get("voice_speed"))
        self._txt_workspace.setText(s.get("workspace_dir"))
        self._txt_cookies.setText(s.get("cookies_path"))
        self._txt_ffmpeg.setText(s.get("ffmpeg_path"))
        self._txt_img_output.setText(s.get("image_output_dir"))
        self._txt_vid_output.setText(s.get("video_output_dir"))
        self._spn_concurrent.setValue(s.get_int("max_concurrent") or 3)
        self._spn_retries.setValue(s.get_int("max_retries") or 3)

        # Update session status
        if s.get("gemini_session_token"):
            self._lbl_session_status.setText("🟢 Token saved")
            self._lbl_session_status.setStyleSheet("color: #1ed760; font-size: 11px;")
        else:
            self._lbl_session_status.setText("🔴 No token")
            self._lbl_session_status.setStyleSheet("color: #e74c3c; font-size: 11px;")

    def _save_settings(self):
        s = get_settings()
        s.set_many({
            "llm_endpoint": self._txt_llm_endpoint.text().strip(),
            "api_key": self._txt_api_key.text().strip(),
            "llm_model": self._txt_llm_model.text().strip(),
            "llm_temperature": str(self._spn_temperature.value()),
            "llm_max_tokens": str(self._spn_max_tokens.value()),
            "image_endpoint": self._txt_image_endpoint.text().strip(),
            "image_api_key": self._txt_image_api_key.text().strip(),
            "image_model": self._cmb_image_model.currentText(),
            "image_style_prefix": self._txt_style_prefix.text().strip(),
            "gemini_api_key": self._txt_gemini_key.text().strip(),
            "gemini_session_token": self._txt_session.text().strip(),
            "gemini_model": self._cmb_gemini_model.currentText(),
            "voice_engine": self._cmb_voice_engine.currentData(),
            "omnivoice_url": self._txt_omnivoice_url.text().strip(),
            "edge_tts_voice": self._cmb_default_voice.currentText(),
            "voice_speed": self._txt_voice_speed.text().strip(),
            "whisper_model": self._cmb_whisper.currentText(),
            "device": self._cmb_device.currentText(),
            "target_language": self._cmb_target_lang.currentData(),
            "target_duration": str(self._spn_target_dur.value()),
            "platform": self._cmb_platform.currentData(),
            "anti_reup_preset": self._cmb_antireup.currentData(),
            "mismatch_strategy": self._cmb_mismatch.currentText(),
            "transition_type": self._cmb_transition.currentText(),
            "segment_crop": str(self._spn_crop.value() / 100.0),
            "max_concurrent": str(self._spn_concurrent.value()),
            "max_retries": str(self._spn_retries.value()),
            "auto_retry": str(self._chk_auto_retry.isChecked()),
            "auto_timeline": str(self._chk_auto_timeline.isChecked()),
            "workspace_dir": self._txt_workspace.text().strip(),
            "cookies_path": self._txt_cookies.text().strip(),
            "ffmpeg_path": self._txt_ffmpeg.text().strip(),
            "image_output_dir": self._txt_img_output.text().strip(),
            "video_output_dir": self._txt_vid_output.text().strip(),
            "cache_pipeline": str(self._chk_cache_pipeline.isChecked()),
            "sanitize_content": str(self._chk_sanitize.isChecked()),
            "scene_detection": str(self._chk_scene_detect.isChecked()),
            "keep_temp": str(self._chk_keep_temp.isChecked()),
            "log_retention_days": str(self._spn_log_days.value()),
        })
        self._main.set_status("Settings saved!")
        QMessageBox.information(self, "Settings", "All settings saved successfully!")

    def _login_google(self):
        """Open browser for Google login to get session token."""
        try:
            from services.google_auth import login_google_get_session
            self._main.set_status("Opening browser for Google login...")
            token = login_google_get_session(headless=False)
            if token:
                self._txt_session.setText(token)
                self._lbl_session_status.setText("🟢 Token obtained!")
                self._lbl_session_status.setStyleSheet("color: #1ed760; font-size: 11px;")
                # Auto-save
                get_settings().set("gemini_session_token", token)
            else:
                # Fallback: open browser manually
                from services.google_auth import login_google_simple
                login_google_simple()
                QMessageBox.information(self, "Google Login",
                    "Browser opened. After login:\n"
                    "1. Go to: https://labs.google/fx/api/auth/session\n"
                    "2. Copy the accessToken value\n"
                    "3. Paste it in the Session Token field above\n"
                    "4. Click Save Settings")
        except Exception as e:
            QMessageBox.warning(self, "Login Error", f"Failed: {str(e)}\n\nInstall Playwright: pip install playwright && playwright install chromium")

    def _check_session(self):
        """Check if session token is valid."""
        token = self._txt_session.text().strip()
        if not token:
            self._lbl_session_status.setText("🔴 No token")
            self._lbl_session_status.setStyleSheet("color: #e74c3c; font-size: 11px;")
            return

        from services.google_auth import check_session_valid
        # Save first so check_session_valid can read it
        get_settings().set("gemini_session_token", token)

        if check_session_valid():
            self._lbl_session_status.setText("🟢 Valid!")
            self._lbl_session_status.setStyleSheet("color: #1ed760; font-size: 11px;")
        else:
            self._lbl_session_status.setText("🔴 Expired/Invalid")
            self._lbl_session_status.setStyleSheet("color: #e74c3c; font-size: 11px;")

    def _reset_defaults(self):
        reply = QMessageBox.question(self, "Reset", "Reset all settings to defaults?")
        if reply == QMessageBox.StandardButton.Yes:
            # Clear DB and reload
            s = get_settings()
            for key in list(s._cache.keys()):
                s._cache.pop(key)
            self._load_settings()
            self._main.set_status("Settings reset to defaults")

    def _browse_path(self, txt_widget: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "Select folder")
        if path:
            txt_widget.setText(path)
