"""
Compose Page — Scene-based Timeline Editor + Preview + Compose
Mỗi scene = 1 card (visual + voice + subtitle + duration).
INPUT: project folder (auto-detect SRT + voice + visuals)
OUTPUT: compose/composed_final.mp4
"""

import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame, QFileDialog, QProgressBar,
    QTextEdit, QCheckBox, QSplitter, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

from ui.widgets.scene_timeline import SceneTimeline, SceneData
from ui.widgets.preview_widget import PreviewWidget


class ComposePage(QWidget):
    """Compose page with Scene Timeline + Preview + Compose action."""

    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._worker = None
        self._project_dir = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main splitter: Preview (top) | Scene Timeline (bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # === Preview Panel ===
        self._preview = PreviewWidget()
        splitter.addWidget(self._preview)

        # === Scene Timeline ===
        self._timeline = SceneTimeline()
        self._timeline.scene_selected.connect(self._on_scene_selected)
        self._timeline.scenes_changed.connect(self._on_scenes_changed)
        splitter.addWidget(self._timeline)

        # 40% preview, 60% timeline
        splitter.setSizes([320, 480])
        layout.addWidget(splitter, 1)

        # === Bottom Controls Panel ===
        controls = QFrame()
        controls.setStyleSheet("background: #141422; border-top: 1px solid #2d2d44; padding: 8px;")
        cl = QVBoxLayout(controls)
        cl.setContentsMargins(16, 8, 16, 8)
        cl.setSpacing(8)

        # Project path row
        row_proj = QHBoxLayout()
        row_proj.addWidget(QLabel("Project:"))
        self._txt_project = QLineEdit()
        self._txt_project.setPlaceholderText("Select project folder (chứa SRT + voice_segments + visuals)")
        self._txt_project.setReadOnly(True)
        row_proj.addWidget(self._txt_project)
        btn_proj = QPushButton("📂 Load")
        btn_proj.setObjectName("SecondaryButton")
        btn_proj.clicked.connect(self._browse_project)
        row_proj.addWidget(btn_proj)
        cl.addLayout(row_proj)

        # Options row
        opts = QHBoxLayout()

        self._chk_sub = QCheckBox("Burn subtitle")
        self._chk_sub.setChecked(True)
        opts.addWidget(self._chk_sub)

        opts.addWidget(QLabel("Transition:"))
        self._cmb_trans = QComboBox()
        self._cmb_trans.addItems(["none", "crossfade", "fade_black"])
        opts.addWidget(self._cmb_trans)

        opts.addWidget(QLabel("Mismatch:"))
        self._cmb_mm = QComboBox()
        self._cmb_mm.addItems(["freeze_last", "slow_video", "trim_voice"])
        opts.addWidget(self._cmb_mm)

        opts.addStretch()

        # Compose button
        self._btn = QPushButton("🎬 COMPOSE")
        self._btn.setObjectName("PrimaryButton")
        self._btn.setMinimumHeight(36)
        self._btn.setMinimumWidth(180)
        self._btn.clicked.connect(self._compose)
        opts.addWidget(self._btn)

        cl.addLayout(opts)

        # Progress + Log
        prog_row = QHBoxLayout()
        self._progress = QProgressBar()
        self._progress.setMaximumHeight(18)
        prog_row.addWidget(self._progress)

        self._btn_cancel = QPushButton("✕ Cancel")
        self._btn_cancel.setObjectName("SecondaryButton")
        self._btn_cancel.setFixedWidth(80)
        self._btn_cancel.setVisible(False)
        self._btn_cancel.clicked.connect(self._cancel)
        prog_row.addWidget(self._btn_cancel)
        cl.addLayout(prog_row)

        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMaximumHeight(100)
        self._txt_log.setStyleSheet(
            "font-family: Consolas; font-size: 11px; background: #0d0d1a; "
            "border: 1px solid #2d2d44; color: #ccc;"
        )
        cl.addWidget(self._txt_log)

        layout.addWidget(controls)

    def _browse_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Select project folder")
        if folder:
            self._load_project(folder)

    def _load_project(self, folder: str):
        """Load project folder into scene timeline."""
        self._project_dir = folder
        self._txt_project.setText(folder)
        self._timeline.clear()
        self._timeline.load_project_folder(folder)

        # Preview first scene
        scenes = self._timeline.get_scenes()
        if scenes and scenes[0].visual_path:
            self._preview.load_file(scenes[0].visual_path)

        # Log summary
        self._txt_log.clear()
        self._txt_log.append(f"📂 Loaded: {folder}")
        self._txt_log.append(f"   Scenes: {self._timeline.get_scene_count()}")
        total = self._timeline.get_total_duration()
        self._txt_log.append(f"   Total duration: {int(total//60)}:{int(total%60):02d}")

        # Count assets
        with_visual = sum(1 for s in scenes if s.visual_path)
        with_voice = sum(1 for s in scenes if s.voice_path)
        with_sub = sum(1 for s in scenes if s.subtitle_text)
        self._txt_log.append(f"   Visuals: {with_visual} | Voice: {with_voice} | Subtitles: {with_sub}")

    def _on_scene_selected(self, scene: SceneData):
        """When a scene card is clicked, preview its visual."""
        if scene.visual_path and os.path.isfile(scene.visual_path):
            self._preview.load_file(scene.visual_path)
        # Show subtitle
        if scene.subtitle_text:
            self._preview.set_subtitle(scene.subtitle_text)
        else:
            self._preview.set_subtitle("")

    def _on_scenes_changed(self):
        """Update info when scenes are modified."""
        total = self._timeline.get_total_duration()
        count = self._timeline.get_scene_count()
        m, s = divmod(int(total), 60)
        self._txt_log.append(f"   → {count} scenes, {m}:{s:02d} total")

    def _compose(self):
        """Read scenes and compose video."""
        scenes = self._timeline.get_scenes()
        if not scenes:
            self._txt_log.append("⚠ No scenes. Load a project first.")
            return

        # Check at least some scenes have visuals
        with_visual = [s for s in scenes if s.visual_path and os.path.isfile(s.visual_path)]
        if not with_visual:
            self._txt_log.append("⚠ No scenes have visual files. Add images/clips first.")
            return

        # Determine output dir
        if self._project_dir:
            output_dir = os.path.join(self._project_dir, "compose")
        else:
            output_dir = QFileDialog.getExistingDirectory(self, "Select output folder")
            if not output_dir:
                return

        # Find SRT path for subtitle burn
        srt_path = None
        if self._chk_sub.isChecked() and self._project_dir:
            for f in os.listdir(self._project_dir):
                if f.endswith(".srt"):
                    if "rewritten" in f.lower():
                        srt_path = os.path.join(self._project_dir, f)
                        break
                    elif not srt_path:
                        srt_path = os.path.join(self._project_dir, f)

        # Build config from scenes
        config = {
            "mode": "scenes",
            "scenes": [s.to_dict() for s in scenes],
            "output_dir": output_dir,
            "burn_subtitle": self._chk_sub.isChecked(),
            "srt_path": srt_path,
            "transition": self._cmb_trans.currentText(),
            "mismatch": self._cmb_mm.currentText(),
            "total_duration": self._timeline.get_total_duration(),
        }

        self._btn.setEnabled(False)
        self._btn.setText("⏳ Composing...")
        self._btn_cancel.setVisible(True)
        self._progress.setValue(0)
        self._txt_log.clear()
        self._txt_log.append(f"🎬 Composing {len(scenes)} scenes...")
        self._txt_log.append(f"   Output: {output_dir}")

        from workers.compose_worker import ComposeWorker
        self._worker = ComposeWorker(config)
        self._worker.progress.connect(self._on_progress)
        self._worker.log_message.connect(lambda m: self._txt_log.append(m))
        self._worker.finished.connect(self._done)
        self._worker.error.connect(self._err)
        self._worker.start()

    def _on_progress(self, pct, msg):
        self._progress.setValue(pct)
        if msg:
            self._txt_log.append(msg)

    def _done(self, path):
        self._btn.setEnabled(True)
        self._btn.setText("🎬 COMPOSE")
        self._btn_cancel.setVisible(False)
        self._progress.setValue(100)
        self._txt_log.append(f"\n✅ Output: {path}")
        self._txt_log.append("→ Chuyển sang Export để xuất final.")
        # Load result into preview
        if os.path.isfile(path):
            self._preview.load_file(path)

    def _err(self, msg):
        self._btn.setEnabled(True)
        self._btn.setText("🎬 COMPOSE")
        self._btn_cancel.setVisible(False)
        self._txt_log.append(f"\n❌ {msg}")

    def _cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker._cancelled = True
            self._txt_log.append("⏹ Cancelling...")

    # === Public API for project flow integration ===

    def load_from_project(self, project_dir: str):
        """Called by other pages to auto-load project into Compose."""
        self._load_project(project_dir)
