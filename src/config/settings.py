"""
Video Reup Studio Rebuild — SQLite-backed Settings (learned from NAVTools)
Thread-safe, cached, with defaults.
"""

import os
import sqlite3
import threading
from typing import Any


class Settings:
    """Key-value settings store backed by SQLite."""

    DEFAULTS = {
        # LLM
        "llm_endpoint": "http://localhost:20128/v1",
        "llm_model": "auto",
        "llm_temperature": "0.3",
        # TTS
        "voice_engine": "omnivoice",
        "voice_id": "",
        "edge_tts_voice": "it-IT-DiegoNeural",
        # Download
        "cookies_path": "",
        "max_resolution": "1080",
        # Pipeline
        "target_language": "it",
        "platform": "tiktok",
        "anti_reup_preset": "medium",
        "mismatch_strategy": "freeze_last",
        "subtitle_enabled": "true",
        "anti_reup_enabled": "true",
        "split_enabled": "true",
        "segment_crop": "0.03",
        # Whisper
        "whisper_model": "large-v3",
        "device": "cuda",
        # Workspace
        "workspace_dir": "",
        # UI
        "theme": "dark",
        "last_page": "source",
    }

    def __init__(self, db_path: str = None):
        if db_path is None:
            from config.constants import PROJECT_ROOT
            db_path = os.path.join(PROJECT_ROOT, "settings.db")

        self._db_path = db_path
        self._lock = threading.Lock()
        self._cache: dict[str, str] = {}
        self._init_db()
        self._load_all()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()
            conn.close()

    def _load_all(self):
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            conn.close()
            self._cache = {k: v for k, v in rows}

    def get(self, key: str, default: str = None) -> str:
        """Get setting value. Falls back to DEFAULTS then to provided default."""
        if key in self._cache:
            return self._cache[key]
        if key in self.DEFAULTS:
            return self.DEFAULTS[key]
        return default or ""

    def get_bool(self, key: str) -> bool:
        return self.get(key, "false").lower() in ("true", "1", "yes")

    def get_float(self, key: str) -> float:
        try:
            return float(self.get(key, "0"))
        except ValueError:
            return 0.0

    def get_int(self, key: str) -> int:
        try:
            return int(self.get(key, "0"))
        except ValueError:
            return 0

    def set(self, key: str, value: Any):
        """Set a setting value. Persists immediately."""
        value_str = str(value)
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value_str)
            )
            conn.commit()
            conn.close()
            self._cache[key] = value_str

    def set_many(self, items: dict):
        """Set multiple values at once."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            for key, value in items.items():
                value_str = str(value)
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (key, value_str)
                )
                self._cache[key] = value_str
            conn.commit()
            conn.close()

    def all(self) -> dict[str, str]:
        """Get all settings (defaults merged with saved)."""
        result = dict(self.DEFAULTS)
        result.update(self._cache)
        return result


# Singleton
_instance: Settings | None = None


def get_settings() -> Settings:
    global _instance
    if _instance is None:
        _instance = Settings()
    return _instance
