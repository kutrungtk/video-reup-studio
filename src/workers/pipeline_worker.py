"""
Video Reup Studio Rebuild — Pipeline Worker
QThread-based worker for running pipeline with cancel/pause support.
Learned from NAVTools TaskManager pattern.
"""

import json
import os
import sys
import time
import traceback
from PySide6.QtCore import QThread, Signal


class PipelineWorker(QThread):
    """Run pipeline_v2 in background thread with progress signals."""

    # Signals
    progress = Signal(int, str)      # (percent, message)
    log_message = Signal(str)        # log line
    finished = Signal(dict)          # summary dict
    error = Signal(str)              # error message

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        self._cancelled = False
        self._paused = False

    def run(self):
        """Execute pipeline in thread."""
        try:
            # Add engine paths so pipeline_v2 can import modules
            from config.constants import PROJECT_ROOT
            engine_dir = os.path.join(PROJECT_ROOT, "src", "engine")
            modules_dir = os.path.join(engine_dir, "modules")

            for p in [engine_dir, modules_dir]:
                if p not in sys.path:
                    sys.path.insert(0, p)

            # Import pipeline
            from engine.pipeline_v2 import PipelineConfig, PipelineV2

            # Build config — filter only valid PipelineConfig fields
            valid_fields = set(PipelineConfig.__dataclass_fields__.keys())
            filtered = {}
            for k, v in self._config.items():
                if k in valid_fields:
                    # Convert booleans from string if needed
                    field_type = PipelineConfig.__dataclass_fields__[k].type
                    if field_type == 'bool' and isinstance(v, str):
                        filtered[k] = v.lower() in ('true', '1', 'yes')
                    elif field_type == 'float' and isinstance(v, (int, str)):
                        filtered[k] = float(v)
                    else:
                        filtered[k] = v

            config = PipelineConfig(**filtered)

            # Ensure output dir exists
            os.makedirs(config.output_dir, exist_ok=True)

            # Create pipeline
            pipeline = PipelineV2(config)

            # Monkey-patch _progress to emit signals + check cancel/pause
            original_progress = pipeline._progress

            def patched_progress(step, step_num, message):
                # Check cancel
                if self._cancelled:
                    raise InterruptedError("Pipeline cancelled by user")
                # Check pause
                while self._paused:
                    time.sleep(0.2)
                    if self._cancelled:
                        raise InterruptedError("Pipeline cancelled by user")

                # Emit progress
                original_progress(step, step_num, message)
                total = len(pipeline.STEPS)
                percent = round((step_num / total) * 100) if step_num > 0 else 0
                self.progress.emit(percent, message)
                self.log_message.emit(f"[{percent}%] {message}")

            pipeline._progress = patched_progress

            # Also capture print output from engine modules
            self.log_message.emit(f"Pipeline starting: {config.output_dir}")
            self.log_message.emit(f"Target: {config.target_language} | Platform: {config.split_platform}")

            # Run pipeline
            summary = pipeline.run()

            if not self._cancelled:
                self.finished.emit(summary)

        except InterruptedError:
            self.log_message.emit("⚠ Pipeline cancelled.")
            self.error.emit("Cancelled by user")
        except Exception as e:
            tb = traceback.format_exc()
            self.log_message.emit(f"❌ Error: {str(e)}\n{tb}")
            self.error.emit(str(e))

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True

    def pause(self):
        """Pause pipeline execution."""
        self._paused = True
        self.log_message.emit("⏸ Pipeline paused")

    def resume(self):
        """Resume pipeline execution."""
        self._paused = False
        self.log_message.emit("▶ Pipeline resumed")

    @property
    def is_running(self) -> bool:
        return self.isRunning() and not self._cancelled
