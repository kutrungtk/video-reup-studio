# Video Reup Studio Rebuild — Spec

## Overview
PySide6 desktop app for automated video reup workflow.
Single language (Python), learned from NAVTools architecture.

## Tech Stack
- **GUI**: PySide6 (Qt for Python), dark theme
- **Engine**: Python (FFmpeg, WhisperX, OmniVoice, Edge-TTS)
- **LLM**: 9router (localhost:20128/v1) with fallback chain
- **DB**: SQLite (settings + task state)
- **Package**: PyInstaller → single EXE

## Workflow
1. Source → Download (yt-dlp) or browse local
2. Script → Transcribe (Whisper) + AI Rewrite (LLM)
3. Voice → TTS per segment (OmniVoice CUDA + Edge-TTS fallback)
4. Compose → Cut video by SRT + merge voice + subtitle + transitions
5. Timeline → Visual editor (3 tracks, split/trim/delete)
6. Export → Anti-reup + Split for platform + Output

## Key Patterns (from NAVTools)
- QThread-based TaskManager with cancel/pause
- LLM fallback chain (multi-model)
- SQLite settings (key-value, cached)
- Lazy page loading
- Pipeline caching (resume interrupted)
