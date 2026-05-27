"""
Video Reup Studio Rebuild — Configuration Constants
"""

APP_NAME = "Video Reup Studio"
APP_VERSION = "3.0.0"
APP_AUTHOR = "HoangTrung"

# Paths
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE_DIR = os.path.join(PROJECT_ROOT, "workspace")
FFMPEG_BIN = os.path.join(PROJECT_ROOT, "ffmpeg_bin")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")

# LLM
DEFAULT_LLM_ENDPOINT = "http://localhost:20128/v1"
LLM_FALLBACK_MODELS = [
    "auto",  # let 9router decide
]

# TTS
OMNIVOICE_URL = "http://localhost:8100/tts"
EDGE_TTS_FALLBACK = True

# Supported languages
LANGUAGES = {
    "it": "Italian",
    "en": "English",
    "vi": "Vietnamese",
    "zh": "Chinese",
    "ko": "Korean",
    "ja": "Japanese",
}

# Platforms — chỉ định aspect ratio, fps, audio, duration
# Resolution được tính từ Platform × Quality (Full HD / 2K)
PLATFORMS = {
    "tiktok":    {"label": "🎵 TikTok", "aspect": "9:16", "fps": 30, "max_duration": 600, "audio_br": "192k", "audio_sr": "44100"},
    "yt_shorts": {"label": "▶️ YouTube Shorts", "aspect": "9:16", "fps": 30, "max_duration": 180, "audio_br": "384k", "audio_sr": "48000"},
    "youtube":   {"label": "▶️ YouTube", "aspect": "16:9", "fps": 30, "max_duration": 3600, "audio_br": "384k", "audio_sr": "48000"},
    "fb_reels":  {"label": "📘 Facebook Reels", "aspect": "9:16", "fps": 30, "max_duration": 90, "audio_br": "192k", "audio_sr": "44100"},
    "fb_feed":   {"label": "📘 Facebook Feed", "aspect": "16:9", "fps": 30, "max_duration": 14400, "audio_br": "192k", "audio_sr": "44100"},
    "ig_reels":  {"label": "📷 Instagram Reels", "aspect": "9:16", "fps": 30, "max_duration": 90, "audio_br": "192k", "audio_sr": "44100"},
}

# Quality presets — resolution tự tính theo aspect
# 9:16 → w×h = short_side × long_side (vertical)
# 16:9 → w×h = long_side × short_side (horizontal)
QUALITY_PRESETS = {
    "fullhd": {"label": "Full HD 1080p", "short": 1080, "long": 1920, "crf": 18, "maxrate": "20M", "bufsize": "30M", "level": "4.2"},
    "2k":     {"label": "2K 1440p", "short": 1440, "long": 2560, "crf": 18, "maxrate": "30M", "bufsize": "45M", "level": "5.1"},
}

def get_encode_params(platform_key: str, quality_key: str) -> dict:
    """Tính encode params từ Platform × Quality."""
    platform = PLATFORMS.get(platform_key, PLATFORMS["tiktok"])
    quality = QUALITY_PRESETS.get(quality_key, QUALITY_PRESETS["fullhd"])
    
    # Tính resolution theo aspect
    if platform["aspect"] == "9:16":
        w, h = quality["short"], quality["long"]
    else:  # 16:9
        w, h = quality["long"], quality["short"]
    
    return {
        "w": w, "h": h,
        "resolution": f"{w}x{h}",
        "aspect": platform["aspect"],
        "fps": platform["fps"],
        "crf": quality["crf"],
        "maxrate": quality["maxrate"],
        "bufsize": quality["bufsize"],
        "level": quality["level"],
        "audio_br": platform["audio_br"],
        "audio_sr": platform["audio_sr"],
        "max_duration": platform["max_duration"],
        "preset": "medium",  # default CPU, override if GPU detected
    }

# Anti-reup presets
ANTI_REUP_PRESETS = ["light", "medium", "heavy", "tiktok", "youtube"]

# Voice engines
VOICE_ENGINES = ["omnivoice", "edge-tts"]

# UI
SIDEBAR_WIDTH = 220
WINDOW_MIN_WIDTH = 1200
WINDOW_MIN_HEIGHT = 750
