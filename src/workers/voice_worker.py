"""
Video Reup Studio Rebuild — Voice Worker
QThread worker for TTS generation per segment.
"""

import os
import sys
import traceback
from PySide6.QtCore import QThread, Signal


class VoiceWorker(QThread):
    """Generate voice per segment in background."""

    progress = Signal(int, str)
    log_message = Signal(str)
    finished = Signal(str)  # voice_dir
    error = Signal(str)

    def __init__(self, srt_path: str, output_dir: str, config: dict, parent=None):
        super().__init__(parent)
        self._srt_path = srt_path
        self._output_dir = output_dir
        self._config = config
        self._cancelled = False

    def run(self):
        try:
            from config.constants import PROJECT_ROOT
            engine_dir = os.path.join(PROJECT_ROOT, "src", "engine")
            modules_dir = os.path.join(engine_dir, "modules")
            for p in [engine_dir, modules_dir]:
                if p not in sys.path:
                    sys.path.insert(0, p)

            from engine.modules.video_cutter import parse_srt
            from engine.modules.tts_engine import generate_voice_per_segment, VoiceConfig

            self.progress.emit(5, "Loading SRT...")
            segments = parse_srt(self._srt_path)
            if not segments:
                self.error.emit("No segments found in SRT")
                return

            self.log_message.emit(f"Loaded {len(segments)} segments")
            os.makedirs(self._output_dir, exist_ok=True)

            voice_config = VoiceConfig(
                engine=self._config.get("engine", "edge-tts"),
                language=self._config.get("language", "it"),
                speed=self._config.get("speed", 1.0),
                ref_audio=self._config.get("ref_audio", ""),
                instruct=self._config.get("instruct", ""),
                edge_voice=self._config.get("edge_voice", ""),
                device=self._config.get("device", "cuda"),
            )

            def _progress(p, m):
                if self._cancelled:
                    raise InterruptedError()
                self.progress.emit(p, m)
                self.log_message.emit(m)

            def _check():
                if self._cancelled:
                    raise InterruptedError()

            segments = generate_voice_per_segment(
                segments=segments,
                output_dir=self._output_dir,
                config=voice_config,
                progress_cb=_progress,
                check_cancelled=_check,
            )

            success = sum(1 for s in segments if s.voice_path and os.path.isfile(s.voice_path))
            self.log_message.emit(f"\n✅ Done: {success}/{len(segments)} segments voiced")
            self.progress.emit(100, "Voice generation complete!")
            self.finished.emit(self._output_dir)

        except InterruptedError:
            self.log_message.emit("⚠ Cancelled")
            self.error.emit("Cancelled")
        except Exception as e:
            tb = traceback.format_exc()
            self.log_message.emit(f"❌ {str(e)}\n{tb}")
            self.error.emit(str(e))

    def cancel(self):
        self._cancelled = True
