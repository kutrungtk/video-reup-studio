"""
Video Reup Studio Rebuild — Project Manager
Quản lý project folder structure. Mỗi video = 1 project folder.
Tất cả các bước đều lưu file vào đúng chỗ trong project.

Structure:
workspace/
└── 2026-05-25_video-title/
    ├── source.mp4              ← video gốc (download)
    ├── source.srt              ← sub gốc (download hoặc transcribe)
    ├── rewritten.srt           ← sub đã rewrite sang target language
    ├── storyboard.txt          ← kịch bản dựng (visual descriptions)
    ├── voice_segments/         ← voice per segment
    │   ├── seg_001.wav
    │   ├── seg_002.wav
    │   └── ...
    ├── visuals/                ← ảnh AI + video clips per scene
    │   ├── images/
    │   │   ├── scene_001.png
    │   │   └── ...
    │   └── clips/
    │       ├── scene_001.mp4
    │       └── ...
    ├── compose/                ← video thô (ghép xong)
    │   └── composed_final.mp4
    └── output/                 ← video final (anti-reup + split)
        ├── final_tiktok_001.mp4
        └── final_tiktok_002.mp4
"""

import os
import json
from datetime import datetime
from typing import Optional

from config.constants import WORKSPACE_DIR


class ProjectManager:
    """Manages project folder and file paths."""

    def __init__(self, project_dir: str = ""):
        self._project_dir = project_dir

    @classmethod
    def create_new(cls, title: str = "video") -> "ProjectManager":
        """Create new project folder in workspace."""
        title = title.strip().replace(" ", "_") or "video"
        date = datetime.now().strftime("%Y-%m-%d")
        folder_name = f"{date}_{title}"
        project_dir = os.path.join(WORKSPACE_DIR, folder_name)

        # Ensure unique name
        if os.path.exists(project_dir):
            i = 2
            while os.path.exists(f"{project_dir}_{i}"):
                i += 1
            project_dir = f"{project_dir}_{i}"

        os.makedirs(project_dir, exist_ok=True)
        return cls(project_dir)

    @classmethod
    def from_existing(cls, project_dir: str) -> "ProjectManager":
        """Load existing project."""
        return cls(project_dir)

    @property
    def dir(self) -> str:
        return self._project_dir

    # === File paths ===

    @property
    def source_video(self) -> str:
        return os.path.join(self._project_dir, "source.mp4")

    @property
    def source_srt(self) -> str:
        """Find source SRT (any .srt that's not rewritten)."""
        for f in os.listdir(self._project_dir) if os.path.isdir(self._project_dir) else []:
            if f.endswith(".srt") and "rewritten" not in f and "storyboard" not in f:
                return os.path.join(self._project_dir, f)
        return os.path.join(self._project_dir, "source.srt")

    @property
    def rewritten_srt(self) -> str:
        return os.path.join(self._project_dir, "rewritten.srt")

    @property
    def storyboard(self) -> str:
        return os.path.join(self._project_dir, "storyboard.txt")

    @property
    def voice_dir(self) -> str:
        d = os.path.join(self._project_dir, "voice_segments")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def visuals_dir(self) -> str:
        d = os.path.join(self._project_dir, "visuals")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def images_dir(self) -> str:
        d = os.path.join(self._project_dir, "visuals", "images")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def clips_dir(self) -> str:
        d = os.path.join(self._project_dir, "visuals", "clips")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def compose_dir(self) -> str:
        d = os.path.join(self._project_dir, "compose")
        os.makedirs(d, exist_ok=True)
        return d

    @property
    def composed_video(self) -> str:
        return os.path.join(self.compose_dir, "composed_final.mp4")

    @property
    def output_dir(self) -> str:
        d = os.path.join(self._project_dir, "output")
        os.makedirs(d, exist_ok=True)
        return d

    # === Status checks ===

    def has_source_video(self) -> bool:
        return os.path.isfile(self.source_video)

    def has_source_srt(self) -> bool:
        return os.path.isfile(self.source_srt)

    def has_rewritten_srt(self) -> bool:
        return os.path.isfile(self.rewritten_srt)

    def has_storyboard(self) -> bool:
        return os.path.isfile(self.storyboard)

    def has_voice(self) -> bool:
        if not os.path.isdir(self.voice_dir):
            return False
        return any(f.endswith((".wav", ".mp3")) for f in os.listdir(self.voice_dir))

    def has_visuals(self) -> bool:
        clips = self.clips_dir
        if not os.path.isdir(clips):
            return False
        return any(f.endswith(".mp4") for f in os.listdir(clips))

    def has_composed(self) -> bool:
        return os.path.isfile(self.composed_video)

    def has_output(self) -> bool:
        if not os.path.isdir(self.output_dir):
            return False
        return any(f.endswith(".mp4") for f in os.listdir(self.output_dir))

    def get_status(self) -> dict:
        """Get completion status of each step."""
        return {
            "source_video": self.has_source_video(),
            "source_srt": self.has_source_srt(),
            "rewritten_srt": self.has_rewritten_srt(),
            "storyboard": self.has_storyboard(),
            "voice": self.has_voice(),
            "visuals": self.has_visuals(),
            "composed": self.has_composed(),
            "output": self.has_output(),
        }

    def save_meta(self, meta: dict):
        """Save project metadata."""
        path = os.path.join(self._project_dir, "project.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def load_meta(self) -> dict:
        """Load project metadata."""
        path = os.path.join(self._project_dir, "project.json")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
