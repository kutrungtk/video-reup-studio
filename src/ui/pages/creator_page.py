"""
Video Reup Studio Rebuild — Creator Page (Video News / Original Content)
Flow: Script → Scenes → AI Visuals → Voice → Music → Compose → Export

Mục đích: Tạo video news/tin tức từ kịch bản text.
Cũng áp dụng cho: storytelling, educational, review, etc.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QTextEdit, QFrame, QFileDialog,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QGroupBox, QGridLayout, QSpinBox, QCheckBox,
    QTabWidget,
)
from PySide6.QtCore import Qt, QThread, Signal

from config.constants import LANGUAGES


class CreatorPage(QWidget):
    """
    Creator page — build video from script (news, storytelling, etc.)
    
    Workflow:
    1. Write/paste script (or AI generate from topic)
    2. Split into scenes (auto or manual)
    3. Each scene → generate AI image/video OR select local image
    4. Generate voice per scene (OmniVoice clone)
    5. Add background music
    6. Compose: visuals + voice + subtitle + music → final video
    """

    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._scenes = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QLabel("📰 Creator — Video từ kịch bản")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        desc = QLabel("Tạo video news/tin tức/storytelling từ kịch bản text → AI ảnh → voice → nhạc nền → video")
        desc.setStyleSheet("color: #646464; font-size: 11px;")
        layout.addWidget(desc)

        # Tabs for workflow steps
        tabs = QTabWidget()
        tabs.addTab(self._create_script_tab(), "① Kịch bản")
        tabs.addTab(self._create_scenes_tab(), "② Scenes")
        tabs.addTab(self._create_visuals_tab(), "③ Visuals")
        tabs.addTab(self._create_audio_tab(), "④ Voice & Music")
        tabs.addTab(self._create_compose_tab(), "⑤ Compose")
        layout.addWidget(tabs, 1)

    # === TAB 1: Script ===
    def _create_script_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # AI Generate from topic
        gen_group = QGroupBox("AI Generate Script (từ chủ đề)")
        gen_layout = QVBoxLayout(gen_group)

        topic_row = QHBoxLayout()
        topic_row.addWidget(QLabel("Chủ đề:"))
        self._txt_topic = QLineEdit()
        self._txt_topic.setPlaceholderText("VD: 'Tin nóng: AI thay thế 50% công việc năm 2026'")
        topic_row.addWidget(self._txt_topic)
        gen_layout.addLayout(topic_row)

        opts_row = QHBoxLayout()
        opts_row.addWidget(QLabel("Phong cách:"))
        self._cmb_style = QComboBox()
        self._cmb_style.addItems([
            "News (tin tức, khách quan)",
            "Storytelling (kể chuyện, hấp dẫn)",
            "Educational (giáo dục, giải thích)",
            "Review (đánh giá, nhận xét)",
            "Viral (gây sốc, hook mạnh)",
        ])
        opts_row.addWidget(self._cmb_style)

        opts_row.addWidget(QLabel("Độ dài:"))
        self._cmb_length = QComboBox()
        self._cmb_length.addItems(["Short (30-60s)", "Medium (1-3 min)", "Long (3-5 min)"])
        opts_row.addWidget(self._cmb_length)

        opts_row.addWidget(QLabel("Ngôn ngữ:"))
        self._cmb_script_lang = QComboBox()
        for code, name in LANGUAGES.items():
            self._cmb_script_lang.addItem(f"{name}", code)
        opts_row.addWidget(self._cmb_script_lang)
        gen_layout.addLayout(opts_row)

        btn_generate = QPushButton("🤖 AI Generate Script")
        btn_generate.setObjectName("PrimaryButton")
        btn_generate.clicked.connect(self._generate_script)
        gen_layout.addWidget(btn_generate)

        layout.addWidget(gen_group)

        # Manual script editor
        edit_group = QGroupBox("Kịch bản (viết tay hoặc paste)")
        edit_layout = QVBoxLayout(edit_group)

        self._txt_script = QTextEdit()
        self._txt_script.setPlaceholderText(
            "Viết kịch bản ở đây...\n\n"
            "Mỗi đoạn (paragraph) sẽ thành 1 scene.\n"
            "Hoặc dùng --- để phân cách scenes.\n\n"
            "VD:\n"
            "Tin nóng hôm nay: Công nghệ AI đang thay đổi thế giới.\n"
            "---\n"
            "Theo báo cáo mới nhất, 50% công việc văn phòng sẽ bị thay thế.\n"
            "---\n"
            "Các chuyên gia khuyên mọi người nên học thêm kỹ năng mới."
        )
        self._txt_script.setMinimumHeight(200)
        edit_layout.addWidget(self._txt_script)

        btn_row = QHBoxLayout()
        btn_load = QPushButton("📂 Load from file")
        btn_load.setObjectName("SecondaryButton")
        btn_load.clicked.connect(self._load_script)
        btn_row.addWidget(btn_load)

        btn_split = QPushButton("✂ Split into Scenes →")
        btn_split.setObjectName("PrimaryButton")
        btn_split.clicked.connect(self._split_scenes)
        btn_row.addWidget(btn_split)
        btn_row.addStretch()
        edit_layout.addLayout(btn_row)

        layout.addWidget(edit_group, 1)
        return tab

    # === TAB 2: Scenes ===
    def _create_scenes_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("Scenes — mỗi scene = 1 segment trong video"))

        # Scene table
        self._tbl_scenes = QTableWidget()
        self._tbl_scenes.setColumnCount(5)
        self._tbl_scenes.setHorizontalHeaderLabels(["#", "Text (narration)", "Duration", "Visual", "Status"])
        self._tbl_scenes.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._tbl_scenes, 1)

        # Actions
        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ Add Scene")
        btn_add.setObjectName("SecondaryButton")
        btn_add.clicked.connect(self._add_scene)
        btn_row.addWidget(btn_add)

        btn_del = QPushButton("🗑 Delete Selected")
        btn_del.setObjectName("SecondaryButton")
        btn_del.clicked.connect(self._delete_scene)
        btn_row.addWidget(btn_del)

        btn_row.addStretch()

        btn_gen_all = QPushButton("🖼 Generate All Visuals →")
        btn_gen_all.setObjectName("PrimaryButton")
        btn_gen_all.clicked.connect(self._generate_all_visuals)
        btn_row.addWidget(btn_gen_all)
        layout.addLayout(btn_row)

        return tab

    # === TAB 3: Visuals ===
    def _create_visuals_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("Visuals — ảnh/video cho mỗi scene"))

        opts = QHBoxLayout()
        opts.addWidget(QLabel("Visual mode:"))
        self._cmb_visual_mode = QComboBox()
        self._cmb_visual_mode.addItems([
            "AI Image (tạo ảnh từ prompt)",
            "Local Images (chọn ảnh có sẵn)",
            "Stock Video (tìm video stock)",
            "Mixed (AI + local)",
        ])
        opts.addWidget(self._cmb_visual_mode)

        opts.addWidget(QLabel("Effect:"))
        self._cmb_effect = QComboBox()
        self._cmb_effect.addItems([
            "Ken Burns (zoom in/out/pan)",
            "Static (ảnh tĩnh)",
            "Parallax (3D depth)",
        ])
        opts.addWidget(self._cmb_effect)
        opts.addStretch()
        layout.addLayout(opts)

        # Image grid preview
        self._txt_visual_log = QTextEdit()
        self._txt_visual_log.setReadOnly(True)
        self._txt_visual_log.setPlaceholderText("Visual generation log...")
        self._txt_visual_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        layout.addWidget(self._txt_visual_log, 1)

        # Progress
        self._progress_visuals = QProgressBar()
        self._progress_visuals.setValue(0)
        layout.addWidget(self._progress_visuals)

        return tab

    # === TAB 4: Voice & Music ===
    def _create_audio_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Voice
        voice_group = QGroupBox("🎙 Voice (narration)")
        vl = QGridLayout(voice_group)

        vl.addWidget(QLabel("Engine:"), 0, 0)
        self._cmb_voice_engine = QComboBox()
        self._cmb_voice_engine.addItem("OmniVoice (clone giọng)", "omnivoice")
        self._cmb_voice_engine.addItem("Edge-TTS (free)", "edge-tts")
        vl.addWidget(self._cmb_voice_engine, 0, 1)

        vl.addWidget(QLabel("Ref Audio (clone):"), 1, 0)
        ref_row = QHBoxLayout()
        self._txt_ref_audio = QLineEdit()
        self._txt_ref_audio.setPlaceholderText("3s+ audio để clone giọng...")
        ref_row.addWidget(self._txt_ref_audio)
        btn_ref = QPushButton("📂")
        btn_ref.setObjectName("SecondaryButton")
        btn_ref.setFixedWidth(36)
        btn_ref.clicked.connect(self._browse_ref)
        ref_row.addWidget(btn_ref)
        vl.addLayout(ref_row, 1, 1)

        vl.addWidget(QLabel("Instruct:"), 2, 0)
        self._txt_voice_instruct = QLineEdit()
        self._txt_voice_instruct.setPlaceholderText("VD: 'giọng MC tin tức, rõ ràng, trang trọng'")
        vl.addWidget(self._txt_voice_instruct, 2, 1)

        btn_gen_voice = QPushButton("🎙 Generate Voice All Scenes")
        btn_gen_voice.setObjectName("PrimaryButton")
        btn_gen_voice.clicked.connect(self._generate_voice)
        vl.addWidget(btn_gen_voice, 3, 0, 1, 2)

        layout.addWidget(voice_group)

        # Background Music
        music_group = QGroupBox("🎵 Background Music")
        ml = QVBoxLayout(music_group)

        music_row = QHBoxLayout()
        music_row.addWidget(QLabel("Music file:"))
        self._txt_music = QLineEdit()
        self._txt_music.setPlaceholderText("(optional) Nhạc nền cho video...")
        music_row.addWidget(self._txt_music)
        btn_music = QPushButton("📂")
        btn_music.setObjectName("SecondaryButton")
        btn_music.setFixedWidth(36)
        btn_music.clicked.connect(self._browse_music)
        music_row.addWidget(btn_music)
        ml.addLayout(music_row)

        vol_row = QHBoxLayout()
        vol_row.addWidget(QLabel("Music volume:"))
        self._spn_music_vol = QSpinBox()
        self._spn_music_vol.setRange(5, 100)
        self._spn_music_vol.setValue(20)
        self._spn_music_vol.setSuffix("%")
        vol_row.addWidget(self._spn_music_vol)

        self._chk_fade_music = QCheckBox("Fade in/out")
        self._chk_fade_music.setChecked(True)
        vol_row.addWidget(self._chk_fade_music)
        vol_row.addStretch()
        ml.addLayout(vol_row)

        layout.addWidget(music_group)

        # Progress
        self._progress_audio = QProgressBar()
        self._progress_audio.setValue(0)
        layout.addWidget(self._progress_audio)

        layout.addStretch()
        return tab

    # === TAB 5: Compose ===
    def _create_compose_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        layout.addWidget(QLabel("Compose — ghép tất cả thành video hoàn chỉnh"))

        opts = QGridLayout()
        opts.addWidget(QLabel("Resolution:"), 0, 0)
        self._cmb_compose_res = QComboBox()
        self._cmb_compose_res.addItems(["1080x1920 (TikTok)", "1920x1080 (YouTube)", "1080x1080 (Facebook)"])
        opts.addWidget(self._cmb_compose_res, 0, 1)

        opts.addWidget(QLabel("Transition:"), 1, 0)
        self._cmb_compose_trans = QComboBox()
        self._cmb_compose_trans.addItems(["Crossfade (0.5s)", "Fade Black", "None"])
        opts.addWidget(self._cmb_compose_trans, 1, 1)

        self._chk_burn_sub = QCheckBox("Burn subtitle vào video")
        self._chk_burn_sub.setChecked(True)
        opts.addWidget(self._chk_burn_sub, 2, 0, 1, 2)

        self._chk_antireup = QCheckBox("Apply anti-reup")
        self._chk_antireup.setChecked(True)
        opts.addWidget(self._chk_antireup, 3, 0, 1, 2)

        layout.addLayout(opts)

        # Compose button
        self._btn_compose = QPushButton("🎬 COMPOSE VIDEO")
        self._btn_compose.setObjectName("PrimaryButton")
        self._btn_compose.setMinimumHeight(40)
        self._btn_compose.setStyleSheet("font-size: 14px; font-weight: bold;")
        self._btn_compose.clicked.connect(self._compose)
        layout.addWidget(self._btn_compose)

        self._progress_compose = QProgressBar()
        self._progress_compose.setValue(0)
        layout.addWidget(self._progress_compose)

        self._txt_compose_log = QTextEdit()
        self._txt_compose_log.setReadOnly(True)
        self._txt_compose_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        layout.addWidget(self._txt_compose_log, 1)

        return tab

    # === Actions ===

    def _generate_script(self):
        topic = self._txt_topic.text().strip()
        if not topic:
            return

        style = self._cmb_style.currentText().split("(")[0].strip()
        length = self._cmb_length.currentText()
        lang_code = self._cmb_script_lang.currentData()

        # TODO: call LLM to generate script
        prompt = f"Topic: {topic}\nStyle: {style}\nLength: {length}\nLanguage: {lang_code}"
        self._txt_script.setPlainText(f"[AI generating script...]\n\nPrompt sent:\n{prompt}")

    def _load_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load script", filter="Text files (*.txt *.md);;SRT (*.srt);;All (*)")
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self._txt_script.setPlainText(f.read())

    def _split_scenes(self):
        text = self._txt_script.toPlainText().strip()
        if not text:
            return

        # Split by --- or double newline
        if "---" in text:
            parts = [p.strip() for p in text.split("---") if p.strip()]
        else:
            parts = [p.strip() for p in text.split("\n\n") if p.strip()]

        self._scenes = parts
        self._tbl_scenes.setRowCount(len(parts))

        for i, scene_text in enumerate(parts):
            self._tbl_scenes.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self._tbl_scenes.setItem(i, 1, QTableWidgetItem(scene_text[:100]))
            # Estimate duration: ~150 words/min narration
            words = len(scene_text.split())
            est_dur = max(3, int(words / 2.5))  # ~2.5 words/sec
            self._tbl_scenes.setItem(i, 2, QTableWidgetItem(f"{est_dur}s"))
            self._tbl_scenes.setItem(i, 3, QTableWidgetItem("⏳ pending"))
            self._tbl_scenes.setItem(i, 4, QTableWidgetItem("ready"))

    def _add_scene(self):
        row = self._tbl_scenes.rowCount()
        self._tbl_scenes.insertRow(row)
        self._tbl_scenes.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self._tbl_scenes.setItem(row, 1, QTableWidgetItem(""))
        self._tbl_scenes.setItem(row, 2, QTableWidgetItem("5s"))
        self._tbl_scenes.setItem(row, 3, QTableWidgetItem("⏳ pending"))
        self._tbl_scenes.setItem(row, 4, QTableWidgetItem("ready"))

    def _delete_scene(self):
        row = self._tbl_scenes.currentRow()
        if row >= 0:
            self._tbl_scenes.removeRow(row)

    def _generate_all_visuals(self):
        self._txt_visual_log.append("Generating visuals for all scenes...")
        # TODO: call AI image gen per scene

    def _generate_voice(self):
        self._progress_audio.setValue(0)
        # TODO: call TTS engine per scene

    def _browse_ref(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select reference audio", filter="Audio (*.wav *.mp3 *.m4a);;All (*)")
        if path:
            self._txt_ref_audio.setText(path)

    def _browse_music(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select background music", filter="Audio (*.mp3 *.wav *.m4a *.ogg);;All (*)")
        if path:
            self._txt_music.setText(path)

    def _compose(self):
        self._txt_compose_log.append("Composing video from scenes...")
        # TODO: compose all scenes into final video
