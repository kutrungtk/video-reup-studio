"""
Video Reup Studio - Pipeline Orchestrator v2
Workflow: Download → Transcribe → Rewrite → Voice → CUT → COMPOSE → Anti-reup → Split → Export
Controlled via JSON config. Outputs progress JSON lines for GUI consumption.
"""

import json
import os
import sys
import time
import shutil
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict, field


@dataclass
class PipelineConfig:
    """Pipeline configuration - all options in one place."""
    # Input
    input_path: str = ""           # Local video path (or empty if youtube_url set)
    youtube_url: str = ""          # YouTube URL to download
    output_dir: str = "output"     # Project output directory
    cookies_path: str = ""         # Cookies for yt-dlp

    # Language
    source_language: Optional[str] = None  # None = auto-detect
    target_language: str = "it"            # Target language for rewrite

    # Voice
    voice_enabled: bool = True
    voice_id: Optional[str] = None  # None = auto-select
    voice_engine: str = "omnivoice"  # omnivoice | edge-tts

    # Subtitle
    subtitle_enabled: bool = True
    subtitle_style: str = "default"
    word_highlight: bool = False

    # Anti-Reup
    anti_reup_enabled: bool = True
    anti_reup_preset: str = "medium"  # light, medium, heavy, tiktok, youtube

    # Compose
    mismatch_strategy: str = "freeze_last"  # freeze_last | slow_video | trim_voice
    segment_crop: float = 0.03              # Per-segment crop (anti-reup)

    # Split
    split_enabled: bool = True
    split_platform: str = "tiktok"   # tiktok | youtube | facebook
    split_duration: float = 60.0     # Max seconds per part (tiktok=60, youtube=600, fb=180)

    # Export
    export_resolution: str = "1080x1920"  # WxH (tiktok=1080x1920, youtube=1920x1080)

    # Engine
    whisper_model: str = "large-v3"
    device: str = "cuda"
    llm_endpoint: str = "http://localhost:20128/v1"  # 9router

    @classmethod
    def from_json(cls, json_path: str) -> "PipelineConfig":
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        valid_fields = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def to_json(self, json_path: str):
        os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)

    def get_platform_settings(self) -> dict:
        """Get platform-specific split/resolution settings."""
        platforms = {
            "tiktok": {"max_duration": 60, "resolution": "1080x1920"},
            "youtube": {"max_duration": 600, "resolution": "1920x1080"},
            "facebook": {"max_duration": 180, "resolution": "1080x1080"},
        }
        return platforms.get(self.split_platform, platforms["tiktok"])


class PipelineV2:
    """
    Main pipeline orchestrator v2.
    
    Key difference from v1:
    - Video is CUT into segments based on SRT timestamps
    - Voice is generated PER SEGMENT
    - Each segment is composed (video + voice) individually
    - Segments are concatenated into final video
    - Anti-reup applied on final (+ per-segment crop during cut)
    """

    STEPS = [
        "download",
        "transcribe",
        "rewrite",
        "voice",
        "cut",
        "compose",
        "anti_reup",
        "split",
        "export",
    ]

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.project_dir = ""
        self.work_dir = ""

    def run(self) -> dict:
        """Execute full pipeline. Returns summary dict."""
        start_time = time.time()

        # Setup project directory
        self.project_dir = self.config.output_dir
        self.work_dir = os.path.join(self.project_dir, "_work")
        os.makedirs(self.project_dir, exist_ok=True)
        os.makedirs(self.work_dir, exist_ok=True)

        self._progress("start", 0, "Pipeline v2 started")

        try:
            # Step 1: Download (if URL provided)
            video_path = self.config.input_path
            if self.config.youtube_url:
                self._progress("download", 1, "Downloading video...")
                video_path, existing_srt = self._step_download()
            else:
                existing_srt = None
                if not video_path or not os.path.isfile(video_path):
                    raise FileNotFoundError(f"Input video not found: {video_path}")

            # Step 2: Transcribe (if no existing SRT)
            self._progress("transcribe", 2, "Transcribing audio...")
            srt_path = self._step_transcribe(video_path, existing_srt)

            # Step 3: AI Rewrite SRT to target language
            self._progress("rewrite", 3, f"Rewriting to {self.config.target_language}...")
            rewritten_srt = self._step_rewrite(srt_path)

            # Step 4: Generate voice PER SEGMENT from rewritten SRT
            self._progress("voice", 4, "Generating voice per segment...")
            segments = self._step_voice(rewritten_srt)

            # Step 5: CUT video into segments based on SRT timestamps
            self._progress("cut", 5, "Cutting video into segments...")
            segments = self._step_cut(video_path, segments)

            # Step 6: COMPOSE — merge video segments + voice segments
            self._progress("compose", 6, "Composing segments...")
            composed_video = self._step_compose(segments, rewritten_srt)

            # Step 7: Anti-reup on final video
            if self.config.anti_reup_enabled:
                self._progress("anti_reup", 7, "Applying anti-reup...")
                final_video = self._step_anti_reup(composed_video)
            else:
                final_video = composed_video

            # Step 8: Split for platform
            if self.config.split_enabled:
                self._progress("split", 8, "Splitting for platform...")
                video_parts = self._step_split(final_video, rewritten_srt)
            else:
                video_parts = [final_video]

            # Step 9: Export (copy to output with proper naming)
            self._progress("export", 9, "Exporting final videos...")
            exports = self._step_export(video_parts)

            # Done
            elapsed = time.time() - start_time
            summary = {
                "status": "success",
                "elapsed_seconds": round(elapsed, 1),
                "input": video_path,
                "output_dir": self.project_dir,
                "exports": exports,
                "total_parts": len(exports),
                "platform": self.config.split_platform,
                "target_language": self.config.target_language,
                "total_segments": len(segments),
            }

            self._progress("done", len(self.STEPS), f"Complete! {len(exports)} videos in {elapsed:.1f}s")

            # Save summary
            summary_path = os.path.join(self.project_dir, "pipeline_summary.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            return summary

        except Exception as e:
            self._progress("error", -1, f"Error: {str(e)}")
            raise

    def _step_download(self) -> tuple[str, Optional[str]]:
        """Download video from URL. Returns (video_path, srt_path_or_None)."""
        from modules.downloader import download_video

        dl_dir = os.path.join(self.work_dir, "download")
        result = download_video(
            url=self.config.youtube_url,
            output_dir=dl_dir,
            cookies_path=self.config.cookies_path or None,
            subtitle_lang=self.config.source_language,
        )

        # Copy to project dir as source.mp4
        source_path = os.path.join(self.project_dir, "source.mp4")
        shutil.copy2(result.video_path, source_path)

        # Copy subtitle if found
        srt_path = None
        if result.subtitle_path:
            srt_dest = os.path.join(self.project_dir, "source.srt")
            shutil.copy2(result.subtitle_path, srt_dest)
            srt_path = srt_dest

        return source_path, srt_path

    def _step_transcribe(self, video_path: str, existing_srt: Optional[str]) -> str:
        """Transcribe video to SRT. Skip if SRT already exists."""
        if existing_srt and os.path.isfile(existing_srt):
            print(f"[Pipeline] Using existing SRT: {existing_srt}")
            return existing_srt

        from modules.transcriber import transcribe

        transcript = transcribe(
            input_path=video_path,
            model_size=self.config.whisper_model,
            language=self.config.source_language,
            device=self.config.device,
        )

        # Save as SRT
        srt_path = os.path.join(self.project_dir, "source.srt")
        transcript.save_srt(srt_path)

        return srt_path

    def _step_rewrite(self, srt_path: str) -> str:
        """Rewrite SRT to target language using LLM. Preserves timestamps."""
        from modules.translator import translate_srt

        output_srt = os.path.join(self.project_dir, "rewritten.srt")
        translate_srt(
            srt_path=srt_path,
            output_path=output_srt,
            target_lang=self.config.target_language,
            llm_endpoint=self.config.llm_endpoint,
        )

        return output_srt

    def _step_voice(self, srt_path: str) -> list:
        """Generate voice per SRT segment. Returns list of Segments with voice_path."""
        from modules.video_cutter import parse_srt, Segment
        from modules.tts_engine import generate_voice_per_segment, VoiceConfig

        segments = parse_srt(srt_path)
        voice_dir = os.path.join(self.project_dir, "voice_segments")
        os.makedirs(voice_dir, exist_ok=True)

        if self.config.voice_enabled:
            voice_config = VoiceConfig(
                engine=self.config.voice_engine,
                language=self.config.target_language,
            )
            segments = generate_voice_per_segment(
                segments=segments,
                output_dir=voice_dir,
                config=voice_config,
            )
        
        return segments

    def _step_cut(self, video_path: str, segments: list) -> list:
        """Cut source video into segments based on SRT timestamps."""
        from modules.video_cutter import cut_video_by_segments

        video_seg_dir = os.path.join(self.project_dir, "video_segments")

        segments = cut_video_by_segments(
            video_path=video_path,
            segments=segments,
            output_dir=video_seg_dir,
            crop_percent=self.config.segment_crop,
            re_encode=True,
        )

        return segments

    def _step_compose(self, segments: list, subtitle_path: str) -> str:
        """Compose all segments into final video."""
        from modules.composer import compose_all_segments, ComposeConfig

        compose_config = ComposeConfig(
            mismatch_strategy=self.config.mismatch_strategy,
            burn_subtitle=self.config.subtitle_enabled,
        )

        final_path = os.path.join(self.work_dir, "composed_final.mp4")

        compose_all_segments(
            segments=segments,
            output_dir=self.work_dir,
            final_output=final_path,
            config=compose_config,
            subtitle_path=subtitle_path if self.config.subtitle_enabled else None,
        )

        return final_path

    def _step_anti_reup(self, video_path: str) -> str:
        """Apply anti-reup effects on final video."""
        from modules.anti_reup import apply_anti_reup, get_preset

        config = get_preset(self.config.anti_reup_preset)
        config.mirror = False  # NEVER flip per spec-v2

        output = os.path.join(self.work_dir, "final_antireup.mp4")
        apply_anti_reup(video_path, output, config)

        return output

    def _step_split(self, video_path: str, srt_path: str) -> list[str]:
        """Split video for target platform."""
        from modules.splitter import smart_split
        from modules.video_cutter import parse_srt

        platform = self.config.get_platform_settings()
        parts_dir = os.path.join(self.work_dir, "parts")

        # Parse SRT for smart split points
        transcript_data = {"segments": [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in parse_srt(srt_path)
        ]}

        parts = smart_split(
            video_path=video_path,
            output_dir=parts_dir,
            target_duration=platform["max_duration"],
            transcript_data=transcript_data,
        )

        return [p["path"] for p in parts]

    def _step_export(self, video_parts: list[str]) -> list[dict]:
        """Export final videos to output directory."""
        exports = []
        output_dir = os.path.join(self.project_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        for i, part_path in enumerate(video_parts, 1):
            output_name = f"final_{self.config.split_platform}_{i:03d}.mp4"
            output_path = os.path.join(output_dir, output_name)
            shutil.copy2(part_path, output_path)

            file_size = os.path.getsize(output_path)
            exports.append({
                "path": output_path,
                "name": output_name,
                "size_mb": round(file_size / (1024 * 1024), 2),
                "part": i,
            })

        return exports

    def _progress(self, step: str, step_num: int, message: str):
        """Output progress as JSON line (for GUI to parse)."""
        total_steps = len(self.STEPS)
        progress = {
            "type": "progress",
            "step": step,
            "step_num": step_num,
            "total_steps": total_steps,
            "percent": round((step_num / total_steps) * 100) if step_num > 0 else 0,
            "message": message,
            "timestamp": time.time(),
        }
        print(json.dumps(progress, ensure_ascii=False), flush=True)


def run_pipeline(config_path: str) -> dict:
    """Run pipeline v2 from config file."""
    config = PipelineConfig.from_json(config_path)
    pipeline = PipelineV2(config)
    return pipeline.run()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pipeline.py <config.json>")
        print("  or:  python pipeline.py --url <youtube_url> --lang <target_lang> --output <dir>")
        sys.exit(1)

    if sys.argv[1] == "--url":
        # Quick CLI mode
        config = PipelineConfig()
        for i, arg in enumerate(sys.argv):
            if arg == "--url" and i + 1 < len(sys.argv):
                config.youtube_url = sys.argv[i + 1]
            elif arg == "--lang" and i + 1 < len(sys.argv):
                config.target_language = sys.argv[i + 1]
            elif arg == "--output" and i + 1 < len(sys.argv):
                config.output_dir = sys.argv[i + 1]
            elif arg == "--cookies" and i + 1 < len(sys.argv):
                config.cookies_path = sys.argv[i + 1]
            elif arg == "--platform" and i + 1 < len(sys.argv):
                config.split_platform = sys.argv[i + 1]

        if not config.youtube_url:
            print("Error: --url required")
            sys.exit(1)

        pipeline = PipelineV2(config)
        summary = pipeline.run()
        print(f"\n{'='*50}")
        print(f"Pipeline v2 complete!")
        print(f"  Parts: {summary['total_parts']}")
        print(f"  Segments: {summary['total_segments']}")
        print(f"  Time: {summary['elapsed_seconds']}s")
        print(f"  Output: {summary['output_dir']}")
    else:
        config_path = sys.argv[1]
        summary = run_pipeline(config_path)
        print(f"\nDone: {summary['total_parts']} parts in {summary['elapsed_seconds']}s")
