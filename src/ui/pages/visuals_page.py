"""
Video Reup Studio Rebuild — Visuals Page (Complete)
Tạo ảnh AI cho từng scene từ STORYBOARD (image prompts) → preview grid → video clips.

INPUT: storyboard.txt (từ bước Script) — format: SCENE | IMAGE_PROMPT_EN | CAMERA | DURATION
OUTPUT: visuals/images/ (ảnh) + visuals/clips/ (video clips)
"""

import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QFrame, QFileDialog, QProgressBar,
    QTextEdit, QScrollArea, QGridLayout, QSizePolicy, QCheckBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QImage


class StoryboardScene:
    """Parsed scene from storyboard file."""
    def __init__(self, index: int, prompt: str, camera: str = "zoom_in", duration: float = 5.0):
        self.index = index
        self.prompt = prompt          # Image prompt (EN)
        self.camera = camera          # Camera effect
        self.duration = duration      # Seconds


def parse_storyboard(filepath: str) -> list[StoryboardScene]:
    """Parse storyboard file → list of scenes with image prompts.
    Supports 2 formats:
    - New (4 cols): SCENE_NUMBER | IMAGE_PROMPT_EN | CAMERA_EFFECT | DURATION_SECONDS
    - Old (5 cols): SCENE_NUMBER | TYPE | VISUAL_DESCRIPTION | CAMERA_MOVE | DURATION_SECONDS
    For old format, skips scenes marked as VIDEO (only processes IMAGE scenes).
    """
    scenes = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                continue
            try:
                index = int(parts[0])
            except ValueError:
                continue

            if len(parts) >= 5:
                # Old format: SCENE | TYPE | DESCRIPTION | CAMERA | DURATION
                scene_type = parts[1].upper()
                if scene_type == "VIDEO":
                    continue  # Skip VIDEO scenes — only gen images for IMAGE scenes
                prompt = parts[2] if len(parts) > 2 else ""
                camera = parts[3] if len(parts) > 3 else "zoom_in"
                try:
                    duration = float(parts[4]) if len(parts) > 4 else 5.0
                except ValueError:
                    duration = 5.0
            else:
                # New format: SCENE | PROMPT | CAMERA | DURATION
                prompt = parts[1] if len(parts) > 1 else ""
                camera = parts[2] if len(parts) > 2 else "zoom_in"
                try:
                    duration = float(parts[3]) if len(parts) > 3 else 5.0
                except ValueError:
                    duration = 5.0

            if prompt:
                scenes.append(StoryboardScene(index, prompt, camera, duration))
    return scenes


class VisualsWorker(QThread):
    """Worker: generate images for all scenes from storyboard prompts."""
    progress = Signal(int, str)
    log = Signal(str)
    image_ready = Signal(int, str)  # (scene_index, image_path) — for live preview
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, scenes: list[StoryboardScene], output_dir: str, config: dict):
        super().__init__()
        self.scenes = scenes
        self.output_dir = output_dir
        self.config = config
        self._cancelled = False
        self._delay = 3.0  # seconds between requests (avoid rate limit)
        self._max_retries = 2  # retry failed scenes

    def run(self):
        try:
            import sys
            from config.constants import PROJECT_ROOT
            engine_dir = os.path.join(PROJECT_ROOT, "src", "engine")
            modules_dir = os.path.join(engine_dir, "modules")
            for p in [engine_dir, modules_dir]:
                if p not in sys.path:
                    sys.path.insert(0, p)

            from services.gemini_image import get_gemini_image_service
            from services.image_search import search_google_images
            from services.visual_effects import image_to_video

            img_dir = os.path.join(self.output_dir, "images")
            vid_dir = os.path.join(self.output_dir, "clips")
            os.makedirs(img_dir, exist_ok=True)
            os.makedirs(vid_dir, exist_ok=True)

            gemini = get_gemini_image_service()
            total = len(self.scenes)
            success = 0
            resolution = self.config.get("resolution", "1080x1920")
            image_source = self.config.get("image_source", "9router")
            use_search_fallback = self.config.get("use_search_fallback", True)

            # Parse resolution to w, h
            w, h = [int(x) for x in resolution.split("x")]

            # Adjust delay based on source
            if image_source == "gemini_session":
                self._delay = 5.0  # Gemini needs more cooldown
            elif image_source == "9router":
                self._delay = 2.0  # Local, faster
            else:
                self._delay = 3.0

            self.log.emit(f"Source: {image_source} | Resolution: {resolution} | Scenes: {total}")
            self.log.emit(f"Mode: sequential, {self._delay}s delay between scenes, {self._max_retries} retries")

            for i, scene in enumerate(self.scenes):
                if self._cancelled:
                    self.log.emit("⏹ Cancelled by user")
                    break

                prompt = scene.prompt
                self.log.emit(f"\n[{i+1}/{total}] {prompt[:60]}...")
                img_path = os.path.join(img_dir, f"scene_{scene.index:03d}.png")

                # Skip if already exists
                if os.path.isfile(img_path) and os.path.getsize(img_path) > 5000:
                    self.log.emit(f"  ⏭ Already exists, skipping")
                    self.image_ready.emit(scene.index, img_path)
                    success += 1
                    self.progress.emit(int((i + 1) / total * 100), f"Visuals: {i+1}/{total}")
                    continue

                # Generate with retry
                generated = self._generate_with_retry(
                    gemini, prompt, img_path, w, h,
                    image_source, use_search_fallback, img_dir
                )

                # Emit image for live preview
                if generated and os.path.isfile(img_path):
                    self.image_ready.emit(scene.index, img_path)

                    # Convert to video clip with scene's camera effect
                    vid_path = os.path.join(vid_dir, f"scene_{scene.index:03d}.mp4")
                    image_to_video(
                        img_path, vid_path,
                        duration=scene.duration,
                        effect=scene.camera,
                        resolution=resolution,
                    )
                    success += 1
                    self.log.emit(f"  ✓ Video clip: {scene.camera} ({scene.duration}s)")
                else:
                    self.log.emit(f"  ✕ Failed after {self._max_retries} retries")

                self.progress.emit(int((i + 1) / total * 100), f"Visuals: {i+1}/{total}")

                # Delay before next scene (avoid rate limit)
                if i < total - 1 and not self._cancelled:
                    import time
                    self.log.emit(f"  ⏳ Waiting {self._delay}s before next...")
                    time.sleep(self._delay)

            self.finished.emit(success)

        except Exception as e:
            import traceback
            self.log.emit(f"❌ {str(e)}\n{traceback.format_exc()}")
            self.error.emit(str(e))

    def _generate_with_retry(self, gemini, prompt, img_path, w, h,
                             image_source, use_search_fallback, img_dir) -> bool:
        """Try to generate image with retries and fallback."""
        import time

        for attempt in range(self._max_retries + 1):
            if self._cancelled:
                return False

            if attempt > 0:
                wait = self._delay * (attempt + 1)  # Exponential backoff
                self.log.emit(f"  ↻ Retry {attempt}/{self._max_retries} (waiting {wait:.0f}s)...")
                time.sleep(wait)

            generated = None

            # Primary source
            if image_source == "9router":
                generated = gemini._generate_via_local(prompt, img_path, w, h)
                if generated:
                    self.log.emit(f"  ✓ 9router OK")
                    return True
            elif image_source == "gemini_session":
                generated = gemini._generate_via_session(prompt, img_path, w, h)
                if generated:
                    self.log.emit(f"  ✓ Gemini session OK")
                    return True
            elif image_source == "google_search":
                from services.image_search import search_google_images
                words = [wd for wd in prompt.split() if len(wd) > 2][:5]
                search_query = " ".join(words)
                results = search_google_images(search_query, img_dir, count=1)
                if results:
                    import shutil
                    shutil.move(results[0], img_path)
                    self.log.emit(f"  ✓ Search OK")
                    return True

            # Fallback to search (only on last retry)
            if not generated and use_search_fallback and attempt == self._max_retries:
                if image_source != "google_search":
                    self.log.emit(f"  Fallback: image search...")
                    from services.image_search import search_google_images
                    words = [wd for wd in prompt.split() if len(wd) > 2][:5]
                    search_query = " ".join(words)
                    results = search_google_images(search_query, img_dir, count=1)
                    if results:
                        import shutil
                        shutil.move(results[0], img_path)
                        return True

        return False

    def cancel(self):
        self._cancelled = True


class ImageThumbnail(QLabel):
    """Clickable image thumbnail for the grid."""
    clicked = Signal(int, str)  # (index, path)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self._path = ""
        self.setFixedSize(160, 200)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #1a1a1a; border: 1px solid #333; border-radius: 4px;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_placeholder()

    def _set_placeholder(self):
        self.setText(f"Scene {self._index}\n⏳")
        self.setStyleSheet("background: #1a1a1a; border: 1px solid #333; border-radius: 4px; color: #646464; font-size: 11px;")

    def set_image(self, path: str):
        self._path = path
        if os.path.isfile(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(158, 198, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.setPixmap(scaled)
                self.setStyleSheet("border: 2px solid #1ed760; border-radius: 4px;")
                return
        self._set_placeholder()

    def mousePressEvent(self, event):
        self.clicked.emit(self._index, self._path)


class VisualsPage(QWidget):
    """Visuals page — generate AI images + preview grid + video clips."""

    def __init__(self, main_window):
        super().__init__()
        self._main = main_window
        self._worker = None
        self._thumbnails: dict[int, ImageThumbnail] = {}
        self._output_dir = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QLabel("🖼 Visuals — Tạo ảnh AI cho từng scene")
        header.setObjectName("SectionHeader")
        layout.addWidget(header)

        # === Input Card ===
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)

        # Storyboard input (NOT SRT)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Storyboard:"))
        self._txt_storyboard = QLineEdit()
        self._txt_storyboard.setPlaceholderText("storyboard.txt (từ bước Script — chứa image prompts)")
        row1.addWidget(self._txt_storyboard)
        btn_sb = QPushButton("📂")
        btn_sb.setObjectName("SecondaryButton")
        btn_sb.setFixedWidth(36)
        btn_sb.clicked.connect(self._browse_storyboard)
        row1.addWidget(btn_sb)
        card_layout.addLayout(row1)

        # Options row 1
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Source:"))
        self._cmb_img_source = QComboBox()
        self._cmb_img_source.addItems([
            "9router (gpt-5.5-image) — 1 ảnh",
            "Gemini Session (ImageFX) — 1~4 ảnh",
            "Google Search",
        ])
        self._cmb_img_source.currentIndexChanged.connect(self._on_source_changed)
        opts.addWidget(self._cmb_img_source)

        opts.addWidget(QLabel("Aspect:"))
        self._cmb_aspect = QComboBox()
        self._cmb_aspect.addItems(["9:16 (Portrait)", "16:9 (Landscape)", "1:1 (Square)"])
        opts.addWidget(self._cmb_aspect)

        opts.addWidget(QLabel("Số ảnh:"))
        self._cmb_count = QComboBox()
        self._cmb_count.addItems(["1", "2", "3", "4"])
        self._cmb_count.setCurrentIndex(0)
        self._cmb_count.setToolTip("Gemini: 1-4 ảnh/scene. 9router: luôn 1.")
        opts.addWidget(self._cmb_count)

        self._chk_fallback = QCheckBox("Google fallback")
        self._chk_fallback.setChecked(True)
        opts.addWidget(self._chk_fallback)
        opts.addStretch()
        card_layout.addLayout(opts)

        # Options row 2: Reference image
        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Ảnh tham chiếu:"))
        self._txt_ref_img = QLineEdit()
        self._txt_ref_img.setPlaceholderText("(optional) Ảnh reference cho style/nhân vật nhất quán")
        ref_row.addWidget(self._txt_ref_img)
        btn_ref = QPushButton("📂")
        btn_ref.setObjectName("SecondaryButton")
        btn_ref.setFixedWidth(36)
        btn_ref.clicked.connect(self._browse_ref_img)
        ref_row.addWidget(btn_ref)

        self._btn_ai_search_ref = QPushButton("🔍 AI Search")
        self._btn_ai_search_ref.setObjectName("SecondaryButton")
        self._btn_ai_search_ref.setToolTip("Dùng AI (gpt-5.5) tự tìm ảnh tham chiếu phù hợp")
        self._btn_ai_search_ref.clicked.connect(self._ai_search_reference)
        ref_row.addWidget(self._btn_ai_search_ref)
        card_layout.addLayout(ref_row)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_generate = QPushButton("🖼 Generate All")
        self._btn_generate.setObjectName("PrimaryButton")
        self._btn_generate.setMinimumHeight(36)
        self._btn_generate.clicked.connect(self._generate)
        btn_row.addWidget(self._btn_generate)

        self._btn_cancel = QPushButton("⏹ Cancel")
        self._btn_cancel.setObjectName("SecondaryButton")
        self._btn_cancel.setStyleSheet("background: #e74c3c; color: white;")
        self._btn_cancel.setVisible(False)
        self._btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self._btn_cancel)

        btn_row.addStretch()

        # Output path display
        self._lbl_output = QLabel("Output: —")
        self._lbl_output.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        btn_row.addWidget(self._lbl_output)

        btn_open = QPushButton("📂 Open")
        btn_open.setObjectName("SecondaryButton")
        btn_open.clicked.connect(self._open_folder)
        btn_row.addWidget(btn_open)

        card_layout.addLayout(btn_row)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        card_layout.addWidget(self._progress)

        layout.addWidget(card)

        # === Image Grid (scrollable) ===
        grid_label = QLabel("Preview — click ảnh để thay thế bằng file khác")
        grid_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(grid_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: #0f0f0f; border: none;")

        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(8)
        scroll.setWidget(self._grid_widget)
        layout.addWidget(scroll, 1)

        # === Log ===
        self._txt_log = QTextEdit()
        self._txt_log.setReadOnly(True)
        self._txt_log.setMaximumHeight(100)
        self._txt_log.setStyleSheet("font-family: Consolas; font-size: 11px;")
        layout.addWidget(self._txt_log)

    # === Actions ===

    def _generate(self):
        sb_path = self._txt_storyboard.text().strip()
        if not sb_path:
            self._txt_log.append("⚠ Select storyboard file (from Script page)")
            return

        if not os.path.isfile(sb_path):
            self._txt_log.append(f"⚠ File not found: {sb_path}")
            return

        # Parse storyboard
        scenes = parse_storyboard(sb_path)
        if not scenes:
            self._txt_log.append("⚠ No scenes found in storyboard. Check format: SCENE | PROMPT | CAMERA | DURATION")
            return

        # Determine output dir (same parent as storyboard)
        self._output_dir = os.path.join(os.path.dirname(sb_path), "visuals")
        self._lbl_output.setText(f"Output: {self._output_dir}")

        # Clear grid
        self._clear_grid()

        # Pre-populate grid with placeholders from storyboard scenes
        self._populate_grid_from_scenes(scenes)

        # Config
        img_source_idx = self._cmb_img_source.currentIndex()
        img_source = ["9router", "gemini_session", "google_search"][img_source_idx]

        # Aspect ratio → resolution mapping
        aspect_map = {"9:16 (Portrait)": "1080x1920", "16:9 (Landscape)": "1920x1080", "1:1 (Square)": "1080x1080"}
        resolution = aspect_map.get(self._cmb_aspect.currentText(), "1080x1920")

        config = {
            "resolution": resolution,
            "image_source": img_source,
            "use_search_fallback": self._chk_fallback.isChecked(),
            "ref_image": self._txt_ref_img.text().strip(),
        }

        self._btn_generate.setEnabled(False)
        self._btn_generate.setText("⏳ Generating...")
        self._btn_cancel.setVisible(True)
        self._progress.setValue(0)
        self._txt_log.clear()
        self._txt_log.append(f"🖼 Generating {len(scenes)} images from storyboard...")

        self._worker = VisualsWorker(scenes, self._output_dir, config)
        self._worker.progress.connect(lambda p, m: self._progress.setValue(p))
        self._worker.log.connect(lambda m: self._txt_log.append(m))
        self._worker.image_ready.connect(self._on_image_ready)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _cancel(self):
        if self._worker:
            self._worker.cancel()

    def _on_image_ready(self, index: int, path: str):
        """Live update: show image in grid as soon as it's generated."""
        if index in self._thumbnails:
            self._thumbnails[index].set_image(path)

    def _on_finished(self, count):
        self._btn_generate.setEnabled(True)
        self._btn_generate.setText("🖼 Generate All")
        self._btn_cancel.setVisible(False)
        self._progress.setValue(100)
        self._txt_log.append(f"\n✅ Done: {count} images generated")
        self._txt_log.append(f"Images: {os.path.join(self._output_dir, 'images')}")
        self._txt_log.append(f"Clips: {os.path.join(self._output_dir, 'clips')}")

    def _on_error(self, msg):
        self._btn_generate.setEnabled(True)
        self._btn_generate.setText("🖼 Generate All")
        self._btn_cancel.setVisible(False)
        self._txt_log.append(f"\n❌ Error: {msg}")

    # === Grid ===

    def _populate_grid_from_scenes(self, scenes: list[StoryboardScene]):
        """Create placeholder thumbnails from storyboard scenes."""
        cols = 5  # thumbnails per row
        for i, scene in enumerate(scenes):
            thumb = ImageThumbnail(scene.index)
            thumb.clicked.connect(self._on_thumb_clicked)
            self._grid_layout.addWidget(thumb, i // cols, i % cols)
            self._thumbnails[scene.index] = thumb

            # Check if image already exists
            img_path = os.path.join(self._output_dir, "images", f"scene_{scene.index:03d}.png")
            if os.path.isfile(img_path):
                thumb.set_image(img_path)

    def _clear_grid(self):
        """Remove all thumbnails from grid."""
        self._thumbnails.clear()
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_thumb_clicked(self, index: int, current_path: str):
        """Click thumbnail → replace with another image."""
        path, _ = QFileDialog.getOpenFileName(
            self, f"Replace image for Scene {index}",
            filter="Images (*.png *.jpg *.jpeg *.webp);;All (*)")
        if path:
            # Copy to visuals/images/
            import shutil
            dest = os.path.join(self._output_dir, "images", f"scene_{index:03d}.png")
            shutil.copy2(path, dest)
            # Update thumbnail
            if index in self._thumbnails:
                self._thumbnails[index].set_image(dest)
            self._txt_log.append(f"Replaced scene {index} image: {os.path.basename(path)}")

    def _open_folder(self):
        """Open output folder in explorer."""
        if self._output_dir and os.path.isdir(self._output_dir):
            import subprocess
            subprocess.Popen(["explorer", self._output_dir.replace("/", "\\")])

    # === Browse ===

    def _browse_storyboard(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Storyboard", filter="Text (*.txt);;All (*)")
        if path:
            self._txt_storyboard.setText(path)

    def _browse_ref_img(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select reference image",
            filter="Images (*.png *.jpg *.jpeg *.webp);;All (*)")
        if path:
            self._txt_ref_img.setText(path)

    def _on_source_changed(self, idx):
        """Update UI based on selected image source."""
        # 9router: count always 1, Gemini: 1-4
        if idx == 0:  # 9router
            self._cmb_count.setCurrentIndex(0)
            self._cmb_count.setEnabled(False)
        elif idx == 1:  # Gemini
            self._cmb_count.setEnabled(True)
        else:  # Google search
            self._cmb_count.setCurrentIndex(0)
            self._cmb_count.setEnabled(False)

    def _ai_search_reference(self):
        """Use AI (LLM) to search for a suitable reference image."""
        sb_path = self._txt_storyboard.text().strip()
        if not sb_path:
            self._txt_log.append("⚠ Load storyboard first to determine search context")
            return

        self._txt_log.append("🔍 AI searching for reference image...")

        try:
            # Read storyboard for context
            with open(sb_path, "r", encoding="utf-8") as f:
                content = f.read()[:500]

            # Ask LLM for search query
            from services.llm_client import get_llm
            llm = get_llm()
            result = llm.chat(
                messages=[{"role": "user", "content": (
                    f"From these image prompts for a video storyboard, suggest ONE image search query (3-5 words) "
                    f"to find a good reference image for consistent visual style.\n"
                    f"Storyboard:\n{content[:400]}\n"
                    f"Output ONLY the search query:"
                )}],
                temperature=0.5,
                max_tokens=20,
            )
            query = result.strip().strip('"')
            self._txt_log.append(f"  Search query: {query}")

            # Search Google
            from services.image_search import search_google_images
            ref_dir = os.path.join(os.path.dirname(sb_path), "reference")
            results = search_google_images(query, ref_dir, count=1)

            if results:
                self._txt_ref_img.setText(results[0])
                self._txt_log.append(f"  ✓ Found: {results[0]}")
            else:
                self._txt_log.append("  ✕ No results found")

        except Exception as e:
            self._txt_log.append(f"  ❌ Error: {e}")

    # === Public API for flow integration ===

    def load_storyboard(self, path: str):
        """Called by Script page to auto-load storyboard into Visuals."""
        self._txt_storyboard.setText(path)
