"""
Video Reup Studio Rebuild — Rewrite Worker
QThread worker for AI rewriting SRT to target language WITH duration/word limit.
"""

import os
import sys
import traceback
from PySide6.QtCore import QThread, Signal


class RewriteWorker(QThread):
    """Rewrite SRT in background thread with duration constraint."""

    progress = Signal(int, str)
    log_message = Signal(str)
    finished = Signal(str)  # output_path
    error = Signal(str)

    def __init__(self, srt_path: str, output_path: str, target_lang: str,
                 target_duration: int = 60, max_words: int = 150, parent=None):
        super().__init__(parent)
        self._srt_path = srt_path
        self._output_path = output_path
        self._target_lang = target_lang
        self._target_duration = target_duration
        self._max_words = max_words

    def run(self):
        try:
            from config.constants import PROJECT_ROOT
            engine_dir = os.path.join(PROJECT_ROOT, "src", "engine")
            modules_dir = os.path.join(engine_dir, "modules")
            for p in [engine_dir, modules_dir]:
                if p not in sys.path:
                    sys.path.insert(0, p)

            from config.settings import get_settings
            settings = get_settings()

            self.progress.emit(10, "Loading SRT...")
            self.log_message.emit(f"Input: {self._srt_path}")
            self.log_message.emit(f"Target: {self._target_lang}, {self._target_duration}s, ~{self._max_words} words")

            # Check if already exists
            if os.path.isfile(self._output_path):
                self.log_message.emit(f"Rewritten SRT already exists: {self._output_path}")
                self.log_message.emit("Delete it to re-generate.")
                self.progress.emit(100, "Already done!")
                self.finished.emit(self._output_path)
                return

            self.progress.emit(20, "Reading original SRT...")

            # Read original SRT
            with open(self._srt_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            self.progress.emit(30, "Calling LLM for rewrite...")

            # Call LLM with duration constraint
            from services.llm_client import get_llm
            llm = get_llm()

            lang_names = {
                "it": "Italian", "en": "English", "vi": "Vietnamese",
                "zh": "Chinese", "ko": "Korean", "ja": "Japanese",
            }
            lang_name = lang_names.get(self._target_lang, self._target_lang)

            prompt = f"""Rewrite this subtitle script into {lang_name} for a {self._target_duration}-second news video.

STRICT RULES:
- Output MUST be maximum {self._max_words} words total (for {self._target_duration}s narration at 2.5 words/sec)
- Condense the content: keep key facts, remove filler
- Write naturally for voice narration (short sentences, clear)
- Output in SRT format with timestamps fitting {self._target_duration} seconds
- Start at 00:00:00,000 and end at 00:00:{self._target_duration:02d},000
- Distribute timestamps evenly across the content
- Each subtitle entry: max 2 lines, max 10 words per line

ORIGINAL SUBTITLE:
{original_content[:4000]}

OUTPUT (SRT format, {lang_name}, max {self._max_words} words, {self._target_duration}s):"""

            result = llm.chat(
                messages=[
                    {"role": "system", "content": f"You are a professional subtitle writer. Condense and translate content to fit exactly {self._target_duration} seconds of narration. Output valid SRT format only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=2048,
            )

            self.progress.emit(80, "Saving rewritten SRT...")

            # Clean up result (remove markdown code blocks if any)
            result = result.strip()
            if result.startswith("```"):
                lines = result.split("\n")
                result = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

            # Save
            os.makedirs(os.path.dirname(self._output_path) or ".", exist_ok=True)
            with open(self._output_path, "w", encoding="utf-8") as f:
                f.write(result)

            # Count words
            word_count = len(result.split())
            self.log_message.emit(f"Output: {self._output_path}")
            self.log_message.emit(f"Words: ~{word_count} (target: {self._max_words})")

            self.progress.emit(100, "Rewrite complete!")
            self.finished.emit(self._output_path)

        except Exception as e:
            tb = traceback.format_exc()
            self.log_message.emit(f"❌ {str(e)}\n{tb}")
            self.error.emit(str(e))
