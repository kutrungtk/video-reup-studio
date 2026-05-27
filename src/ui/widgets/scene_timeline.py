"""
Video Reup Studio Rebuild — Scene Timeline Widget
Scene-based timeline: mỗi scene = 1 card (visual + voice + subtitle + duration).
Học từ NAVTools: đơn giản, trực quan, scene-oriented.
"""

import os
import re
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QFileDialog, QSizePolicy, QMenu,
    QLineEdit, QTextEdit, QSplitter, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QMimeData, QPoint
from PySide6.QtGui import QPixmap, QCursor, QDrag, QFont, QColor, QPainter


class SceneData:
    """Data model for a single scene."""
    def __init__(self, index: int = 1):
        self.index = index
        self.visual_path = ""       # image or video clip path
        self.voice_path = ""        # voice segment path
        self.subtitle_text = ""     # narration text
        self.start_time = 0.0       # start in timeline (seconds)
        self.duration = 5.0         # duration (seconds)
        self.effect = "zoom_in"     # visual effect for images

    @property
    def end_time(self) -> float:
        return self.start_time + self.duration

    @property
    def visual_type(self) -> str:
        """Return 'image', 'video', or 'none'."""
        if not self.visual_path:
            return "none"
        ext = os.path.splitext(self.visual_path)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            return "image"
        elif ext in (".mp4", ".mkv", ".webm", ".avi"):
            return "video"
        return "none"

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "visual_path": self.visual_path,
            "voice_path": self.voice_path,
            "subtitle_text": self.subtitle_text,
            "start_time": self.start_time,
            "duration": self.duration,
            "effect": self.effect,
            "visual_type": self.visual_type,
        }


class SceneCard(QFrame):
    """Visual card for a single scene in the timeline."""

    selected = Signal(object)       # SceneData
    context_menu = Signal(object, QPoint)  # SceneData, position
    double_clicked = Signal(object)  # SceneData — open editor

    THUMB_SIZE = 120
    CARD_WIDTH = 160

    def __init__(self, scene: SceneData, parent=None):
        super().__init__(parent)
        self.scene = scene
        self._is_selected = False
        self._thumb_pixmap = None
        self._setup_ui()
        self._load_thumbnail()

    def _setup_ui(self):
        self.setFixedWidth(self.CARD_WIDTH)
        self.setMinimumHeight(200)
        self.setObjectName("SceneCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Scene number header
        self._lbl_index = QLabel(f"Scene {self.scene.index}")
        self._lbl_index.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_index.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 11px;")
        layout.addWidget(self._lbl_index)

        # Thumbnail
        self._lbl_thumb = QLabel()
        self._lbl_thumb.setFixedSize(self.THUMB_SIZE + 20, self.THUMB_SIZE)
        self._lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_thumb.setStyleSheet(
            "background: #1a1a2e; border: 1px solid #333; border-radius: 4px;"
        )
        layout.addWidget(self._lbl_thumb, 0, Qt.AlignmentFlag.AlignCenter)

        # Visual type badge
        self._lbl_type = QLabel()
        self._lbl_type.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_type.setStyleSheet("font-size: 9px; color: #888;")
        layout.addWidget(self._lbl_type)

        # Voice indicator
        self._lbl_voice = QLabel()
        self._lbl_voice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_voice.setStyleSheet("font-size: 9px;")
        layout.addWidget(self._lbl_voice)

        # Subtitle preview (truncated)
        self._lbl_sub = QLabel()
        self._lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_sub.setWordWrap(True)
        self._lbl_sub.setMaximumHeight(36)
        self._lbl_sub.setStyleSheet("color: #ccc; font-size: 10px;")
        layout.addWidget(self._lbl_sub)

        # Duration
        self._lbl_dur = QLabel()
        self._lbl_dur.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_dur.setStyleSheet("color: #4EC9B0; font-size: 10px; font-weight: bold;")
        layout.addWidget(self._lbl_dur)

        layout.addStretch()
        self.refresh()

    def refresh(self):
        """Update display from scene data."""
        self._lbl_index.setText(f"Scene {self.scene.index}")
        self._load_thumbnail()

        # Type badge
        vtype = self.scene.visual_type
        if vtype == "image":
            self._lbl_type.setText("🖼 Image")
        elif vtype == "video":
            self._lbl_type.setText("🎬 Video")
        else:
            self._lbl_type.setText("⚠ No visual")

        # Voice
        if self.scene.voice_path and os.path.isfile(self.scene.voice_path):
            fname = os.path.basename(self.scene.voice_path)
            self._lbl_voice.setText(f"🔊 {fname}")
            self._lbl_voice.setStyleSheet("font-size: 9px; color: #4ade80;")
        else:
            self._lbl_voice.setText("🔇 No voice")
            self._lbl_voice.setStyleSheet("font-size: 9px; color: #666;")

        # Subtitle
        text = self.scene.subtitle_text
        if text:
            short = text[:40] + "…" if len(text) > 40 else text
            self._lbl_sub.setText(f'"{short}"')
        else:
            self._lbl_sub.setText("(no subtitle)")
            self._lbl_sub.setStyleSheet("color: #555; font-size: 10px; font-style: italic;")

        # Duration
        self._lbl_dur.setText(f"{self.scene.duration:.1f}s")

    def _load_thumbnail(self):
        """Load and display thumbnail."""
        if not self.scene.visual_path or not os.path.isfile(self.scene.visual_path):
            self._lbl_thumb.setText("📷")
            self._lbl_thumb.setStyleSheet(
                "background: #1a1a2e; border: 1px dashed #444; border-radius: 4px; "
                "font-size: 28px; color: #555;"
            )
            return

        ext = os.path.splitext(self.scene.visual_path)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            pixmap = QPixmap(self.scene.visual_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.THUMB_SIZE + 20, self.THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._lbl_thumb.setPixmap(scaled)
                self._lbl_thumb.setStyleSheet(
                    "background: #0a0a0a; border: 1px solid #333; border-radius: 4px;"
                )
                self._thumb_pixmap = scaled
        elif ext in (".mp4", ".mkv", ".webm", ".avi"):
            self._lbl_thumb.setText("🎬")
            self._lbl_thumb.setStyleSheet(
                "background: #1a1a2e; border: 1px solid #333; border-radius: 4px; "
                "font-size: 28px; color: #4d8eff;"
            )

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._update_style()

    def _update_style(self):
        if self._is_selected:
            self.setStyleSheet(
                "QFrame#SceneCard { background: #1e293b; border: 2px solid #3b82f6; border-radius: 8px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame#SceneCard { background: #141422; border: 1px solid #2d2d44; border-radius: 8px; }"
                "QFrame#SceneCard:hover { border-color: #4d4d6a; }"
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.scene)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.scene)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu.emit(self.scene, event.globalPos())


class SceneTimeline(QWidget):
    """Scene-based timeline — horizontal scroll of scene cards."""

    scene_selected = Signal(object)     # SceneData
    scenes_changed = Signal()           # any modification

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scenes: list[SceneData] = []
        self._cards: list[SceneCard] = []
        self._selected_scene: SceneData | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QFrame()
        toolbar.setStyleSheet("background: #1a1a2e; border-bottom: 1px solid #2d2d44;")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(12, 6, 12, 6)

        btn_load = QPushButton("📂 Load Project")
        btn_load.setObjectName("SecondaryButton")
        btn_load.setStyleSheet("font-size: 11px; padding: 4px 10px; font-weight: bold;")
        btn_load.clicked.connect(self._on_load_project)
        tb.addWidget(btn_load)

        tb.addWidget(self._sep())

        btn_add = QPushButton("+ Add Scene")
        btn_add.setObjectName("SecondaryButton")
        btn_add.setStyleSheet("font-size: 11px; padding: 4px 8px;")
        btn_add.clicked.connect(self._on_add_scene)
        tb.addWidget(btn_add)

        btn_del = QPushButton("🗑 Delete")
        btn_del.setObjectName("SecondaryButton")
        btn_del.setStyleSheet("font-size: 11px; padding: 4px 8px;")
        btn_del.clicked.connect(self._on_delete_scene)
        tb.addWidget(btn_del)

        tb.addWidget(self._sep())

        btn_left = QPushButton("◀")
        btn_left.setObjectName("SecondaryButton")
        btn_left.setFixedWidth(28)
        btn_left.clicked.connect(self._on_move_left)
        tb.addWidget(btn_left)

        btn_right = QPushButton("▶")
        btn_right.setObjectName("SecondaryButton")
        btn_right.setFixedWidth(28)
        btn_right.clicked.connect(self._on_move_right)
        tb.addWidget(btn_right)

        tb.addStretch()

        # Scene count + total duration
        self._lbl_info = QLabel("0 scenes | 0:00")
        self._lbl_info.setStyleSheet("color: #888; font-size: 11px;")
        tb.addWidget(self._lbl_info)

        layout.addWidget(toolbar)

        # Scrollable scene cards area
        self._scroll = QScrollArea()
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(False)
        self._scroll.setStyleSheet("background: #0d0d1a; border: none;")
        self._scroll.setMinimumHeight(240)

        self._cards_container = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(12, 8, 12, 8)
        self._cards_layout.setSpacing(8)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._scroll.setWidget(self._cards_container)

        layout.addWidget(self._scroll, 1)

    # === Public API ===

    def get_scenes(self) -> list[SceneData]:
        return self._scenes

    def get_selected_scene(self) -> SceneData | None:
        return self._selected_scene

    def get_total_duration(self) -> float:
        return sum(s.duration for s in self._scenes)

    def get_scene_count(self) -> int:
        return len(self._scenes)

    def clear(self):
        self._scenes.clear()
        self._selected_scene = None
        self._rebuild_cards()

    def load_project_folder(self, project_dir: str):
        """Auto-detect project files and build scenes."""
        self._scenes.clear()

        # 1. Find SRT → parse into scenes
        srt_path = self._find_srt(project_dir)
        segments = []
        if srt_path:
            segments = self._parse_srt(srt_path)

        if not segments:
            # No SRT — try to build from voice files count
            voice_dir = os.path.join(project_dir, "voice_segments")
            if os.path.isdir(voice_dir):
                voice_files = sorted([
                    f for f in os.listdir(voice_dir)
                    if f.endswith((".wav", ".mp3", ".m4a"))
                ])
                for i, vf in enumerate(voice_files):
                    segments.append({
                        "index": i + 1,
                        "start": i * 5.0,
                        "end": (i + 1) * 5.0,
                        "text": "",
                    })

        # 2. Create SceneData from segments
        for seg in segments:
            scene = SceneData(index=seg["index"])
            scene.subtitle_text = seg.get("text", "")
            scene.start_time = seg.get("start", 0)
            scene.duration = seg.get("end", 5) - seg.get("start", 0)
            self._scenes.append(scene)

        # 3. Match voice segments
        voice_dir = os.path.join(project_dir, "voice_segments")
        if os.path.isdir(voice_dir):
            self._match_voice_files(voice_dir)

        # 4. Match visuals (clips or images)
        clips_dir = os.path.join(project_dir, "visuals", "clips")
        images_dir = os.path.join(project_dir, "visuals", "images")
        if os.path.isdir(clips_dir):
            self._match_visual_files(clips_dir, (".mp4", ".mkv", ".webm"))
        elif os.path.isdir(images_dir):
            self._match_visual_files(images_dir, (".png", ".jpg", ".jpeg", ".webp"))
        else:
            # Check for source video
            for f in os.listdir(project_dir):
                if f.startswith("source") and f.endswith((".mp4", ".mkv", ".webm")):
                    source_path = os.path.join(project_dir, f)
                    for scene in self._scenes:
                        scene.visual_path = source_path
                    break

        self._rebuild_cards()
        self.scenes_changed.emit()

    def add_scene(self, scene: SceneData = None):
        """Add a new scene at the end."""
        if scene is None:
            scene = SceneData(index=len(self._scenes) + 1)
            if self._scenes:
                last = self._scenes[-1]
                scene.start_time = last.end_time
                scene.duration = last.duration
        self._scenes.append(scene)
        self._reindex()
        self._rebuild_cards()
        self.scenes_changed.emit()

    def remove_scene(self, scene: SceneData):
        """Remove a scene."""
        if scene in self._scenes:
            self._scenes.remove(scene)
            if self._selected_scene == scene:
                self._selected_scene = None
            self._reindex()
            self._recalc_times()
            self._rebuild_cards()
            self.scenes_changed.emit()

    def move_scene(self, scene: SceneData, direction: int):
        """Move scene left (-1) or right (+1)."""
        idx = self._scenes.index(scene)
        new_idx = idx + direction
        if 0 <= new_idx < len(self._scenes):
            self._scenes[idx], self._scenes[new_idx] = self._scenes[new_idx], self._scenes[idx]
            self._reindex()
            self._recalc_times()
            self._rebuild_cards()
            self.scenes_changed.emit()

    def replace_visual(self, scene: SceneData, path: str):
        """Replace visual for a scene."""
        scene.visual_path = path
        self._refresh_card(scene)
        self.scenes_changed.emit()

    def replace_voice(self, scene: SceneData, path: str):
        """Replace voice for a scene."""
        scene.voice_path = path
        self._refresh_card(scene)
        self.scenes_changed.emit()

    # === Internal ===

    def _find_srt(self, project_dir: str) -> str | None:
        """Find best SRT file in project dir."""
        srt_files = [f for f in os.listdir(project_dir) if f.endswith(".srt")]
        # Prefer rewritten.srt
        for f in srt_files:
            if "rewritten" in f.lower():
                return os.path.join(project_dir, f)
        if srt_files:
            return os.path.join(project_dir, srt_files[0])
        return None

    def _parse_srt(self, srt_path: str) -> list[dict]:
        """Parse SRT into list of {index, start, end, text}."""
        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()
        blocks = re.split(r"\n\s*\n", content.strip())
        segments = []
        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                continue
            match = re.match(
                r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
                lines[1]
            )
            if not match:
                continue
            g = match.groups()
            start = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
            end = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
            text = " ".join(lines[2:]).strip()
            segments.append({
                "index": len(segments) + 1,
                "start": start,
                "end": end,
                "text": text,
            })
        return segments

    def _match_voice_files(self, voice_dir: str):
        """Match voice files to scenes by index."""
        files = sorted([
            f for f in os.listdir(voice_dir)
            if f.endswith((".wav", ".mp3", ".m4a"))
        ])
        for i, scene in enumerate(self._scenes):
            # Try seg_001.wav pattern
            for ext in (".wav", ".mp3", ".m4a"):
                candidate = os.path.join(voice_dir, f"seg_{scene.index:03d}{ext}")
                if os.path.isfile(candidate):
                    scene.voice_path = candidate
                    break
            # Fallback: match by position
            if not scene.voice_path and i < len(files):
                scene.voice_path = os.path.join(voice_dir, files[i])

    def _match_visual_files(self, visuals_dir: str, extensions: tuple):
        """Match visual files to scenes by index."""
        files = sorted([
            f for f in os.listdir(visuals_dir)
            if os.path.splitext(f)[1].lower() in extensions
        ])
        for i, scene in enumerate(self._scenes):
            if i < len(files):
                scene.visual_path = os.path.join(visuals_dir, files[i])

    def _reindex(self):
        """Re-number scenes 1, 2, 3..."""
        for i, scene in enumerate(self._scenes):
            scene.index = i + 1

    def _recalc_times(self):
        """Recalculate start times sequentially."""
        t = 0.0
        for scene in self._scenes:
            scene.start_time = t
            t += scene.duration

    def _rebuild_cards(self):
        """Rebuild all scene cards."""
        # Clear existing
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        # Create new cards
        for scene in self._scenes:
            card = SceneCard(scene)
            card.selected.connect(self._on_card_selected)
            card.context_menu.connect(self._on_card_context_menu)
            card.double_clicked.connect(self._on_card_double_clicked)
            if scene == self._selected_scene:
                card.set_selected(True)
            self._cards_layout.addWidget(card)
            self._cards.append(card)

        # Update container size
        total_w = len(self._cards) * (SceneCard.CARD_WIDTH + 8) + 24
        self._cards_container.setMinimumWidth(total_w)
        self._cards_container.adjustSize()

        # Update info label
        self._update_info()

    def _refresh_card(self, scene: SceneData):
        """Refresh a single card."""
        for card in self._cards:
            if card.scene == scene:
                card.refresh()
                break

    def _update_info(self):
        count = len(self._scenes)
        total = self.get_total_duration()
        m, s = divmod(int(total), 60)
        self._lbl_info.setText(f"{count} scenes | {m}:{s:02d}")

    def _on_card_selected(self, scene: SceneData):
        self._selected_scene = scene
        for card in self._cards:
            card.set_selected(card.scene == scene)
        self.scene_selected.emit(scene)

    def _on_card_context_menu(self, scene: SceneData, pos: QPoint):
        menu = QMenu(self)
        menu.addAction("🖼 Replace visual...", lambda: self._action_replace_visual(scene))
        menu.addAction("🔊 Replace voice...", lambda: self._action_replace_voice(scene))
        menu.addAction("✏ Edit subtitle...", lambda: self._action_edit_subtitle(scene))
        menu.addSeparator()
        menu.addAction("◀ Move left", lambda: self.move_scene(scene, -1))
        menu.addAction("▶ Move right", lambda: self.move_scene(scene, 1))
        menu.addSeparator()
        menu.addAction("🗑 Delete scene", lambda: self.remove_scene(scene))
        menu.exec(pos)

    def _on_card_double_clicked(self, scene: SceneData):
        """Double-click → replace visual."""
        self._action_replace_visual(scene)

    def _action_replace_visual(self, scene: SceneData):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Replace visual — Scene {scene.index}",
            filter="Images/Video (*.png *.jpg *.jpeg *.webp *.mp4 *.mkv *.webm);;All (*)"
        )
        if path:
            self.replace_visual(scene, path)

    def _action_replace_voice(self, scene: SceneData):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Replace voice — Scene {scene.index}",
            filter="Audio (*.wav *.mp3 *.m4a *.aac);;All (*)"
        )
        if path:
            self.replace_voice(scene, path)

    def _action_edit_subtitle(self, scene: SceneData):
        """Simple inline edit via dialog."""
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, f"Edit subtitle — Scene {scene.index}",
            "Subtitle text:", QLineEdit.EchoMode.Normal, scene.subtitle_text
        )
        if ok:
            scene.subtitle_text = text
            self._refresh_card(scene)
            self.scenes_changed.emit()

    # === Toolbar actions ===

    def _on_load_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Select project folder")
        if folder:
            self.load_project_folder(folder)

    def _on_add_scene(self):
        self.add_scene()

    def _on_delete_scene(self):
        if self._selected_scene:
            self.remove_scene(self._selected_scene)

    def _on_move_left(self):
        if self._selected_scene:
            self.move_scene(self._selected_scene, -1)

    def _on_move_right(self):
        if self._selected_scene:
            self.move_scene(self._selected_scene, 1)

    def _sep(self) -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.VLine)
        s.setStyleSheet("color: #333;")
        return s
