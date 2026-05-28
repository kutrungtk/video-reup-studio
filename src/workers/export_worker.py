"""
Video Reup Studio Rebuild — Export Worker
QThread worker for Galaxy Filters + Anti-reup Pro + Split + Encode.
"""

import os
import sys
import random
import shutil
import traceback
from PySide6.QtCore import QThread, Signal


class ExportWorker(QThread):
    """Export video with filters + anti-reup + split."""

    progress = Signal(int, str)
    log_message = Signal(str)
    finished = Signal(list)  # list of output paths
    error = Signal(str)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config

    def run(self):
        try:
            from config.constants import PROJECT_ROOT
            engine_dir = os.path.join(PROJECT_ROOT, "src", "engine")
            modules_dir = os.path.join(engine_dir, "modules")
            for p in [engine_dir, modules_dir]:
                if p not in sys.path:
                    sys.path.insert(0, p)

            from engine.modules.ffmpeg_utils import run_ffmpeg

            input_path = self._config["input_path"]
            output_dir = self._config["output_dir"]
            os.makedirs(output_dir, exist_ok=True)

            current = input_path
            outputs = []

            # Step 1: Galaxy Filter
            filter_str = self._config.get("filter", "")
            if filter_str:
                self.progress.emit(10, "Applying Galaxy Filter...")
                filter_name = self._config.get("filter_name", "custom")
                intensity = self._config.get("filter_intensity", 1.0)
                filtered_path = os.path.join(output_dir, "filtered.mp4")

                # Apply filter with intensity (blend with original)
                if intensity < 1.0:
                    # Use split + overlay for partial intensity
                    vf = f"split[a][b];[b]{filter_str}[filtered];[a][filtered]blend=all_mode=normal:all_opacity={intensity}"
                else:
                    vf = filter_str

                run_ffmpeg([
                    "-i", current,
                    "-vf", vf,
                    "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.2",
                    "-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "17",
                    "-c:a", "copy",
                    "-y", filtered_path,
                ])
                current = filtered_path
                self.log_message.emit(f"🎨 Filter applied: {filter_name}")

            # Step 2: Anti-reup Pro
            techniques = self._config.get("anti_reup_techniques", [])
            if self._config.get("anti_reup_enabled") and techniques:
                self.progress.emit(30, "Applying Anti-reup Pro...")
                current = self._apply_anti_reup_pro(current, output_dir, techniques)
                self.log_message.emit(f"🛡️ Anti-reup: {len(techniques)} techniques applied")

            # Step 3: Speed adjustment
            speed = self._config.get("speed", 1.0)
            if speed != 1.0:
                self.progress.emit(50, f"Adjusting speed ({speed}x)...")
                speed_path = os.path.join(output_dir, "speed.mp4")
                atempo = speed
                # atempo only accepts 0.5-2.0, chain for larger values
                atempo_filters = []
                remaining = atempo
                while remaining > 2.0:
                    atempo_filters.append("atempo=2.0")
                    remaining /= 2.0
                while remaining < 0.5:
                    atempo_filters.append("atempo=0.5")
                    remaining /= 0.5
                atempo_filters.append(f"atempo={remaining:.4f}")

                run_ffmpeg([
                    "-i", current,
                    "-vf", f"setpts={1/speed:.4f}*PTS",
                    "-af", ",".join(atempo_filters),
                    "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.2",
                    "-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "17",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                    "-y", speed_path,
                ])
                current = speed_path
                self.log_message.emit(f"⚡ Speed: {speed}x")

            # Step 4: Split
            if self._config.get("split_enabled", True):
                self.progress.emit(60, "Splitting...")
                max_dur = self._config.get("split_duration", 60)
                video_parts = self._split_video(current, output_dir, max_dur)
                self.log_message.emit(f"✂️ Split: {len(video_parts)} parts ({max_dur}s each)")
            else:
                video_parts = [current]

            # Step 5: Encode final — platform-specific params from config
            self.progress.emit(80, "Encoding final...")
            platform = self._config.get("platform", "tiktok_1080")
            resolution = self._config.get("resolution", "1080x1920")
            crf = self._config.get("crf", 18)
            maxrate = self._config.get("maxrate", "8M")
            bufsize = self._config.get("bufsize", "12M")
            fps = self._config.get("fps", 30)
            level = self._config.get("level", "4.1")
            audio_br = self._config.get("audio_br", "192k")
            audio_sr = self._config.get("audio_sr", "44100")

            for i, part in enumerate(video_parts, 1):
                out_name = f"final_{platform}_{i:03d}.mp4"
                out_path = os.path.join(output_dir, out_name)

                args = ["-i", part]
                vf_parts = []
                if resolution:
                    w, h = resolution.split("x")
                    vf_parts.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
                vf_parts.append(f"fps={fps}")
                args += ["-vf", ",".join(vf_parts)]

                # GPU auto-detect encode
                from engine.modules.gpu_detect import get_encode_command
                quality_key = self._config.get("quality", "fullhd")
                encode_params = get_encode_command(quality_key)
                # Override maxrate/bufsize from config
                final_encode = []
                skip_next = False
                for j, p in enumerate(encode_params):
                    if skip_next:
                        skip_next = False
                        continue
                    if p in ("-maxrate", "-bufsize", "-g"):
                        skip_next = True
                        continue
                    final_encode.append(p)
                final_encode += ["-maxrate", maxrate, "-bufsize", bufsize]
                final_encode += ["-g", str(fps * 2)]
                args += final_encode
                args += ["-c:a", "aac", "-b:a", audio_br, "-ar", audio_sr, "-ac", "2"]
                args += ["-movflags", "+faststart"]
                args += ["-y", out_path]

                run_ffmpeg(args)
                outputs.append(out_path)
                self.log_message.emit(f"✓ {out_name}")

            self.progress.emit(100, "Export complete!")
            self.log_message.emit(f"\n✅ {len(outputs)} files exported to {output_dir}")
            self.finished.emit(outputs)

        except Exception as e:
            tb = traceback.format_exc()
            self.log_message.emit(f"❌ {str(e)}\n{tb}")
            self.error.emit(str(e))

    def _apply_anti_reup_pro(self, input_path: str, output_dir: str, techniques: list) -> str:
        """Apply multiple anti-reup techniques via FFmpeg."""
        from engine.modules.ffmpeg_utils import run_ffmpeg

        current = input_path
        vf_filters = []
        af_filters = []
        extra_args = []

        # Pixel shift (crop edges)
        if "pixel_shift" in techniques:
            crop_px = self._config.get("pixel_crop", 2)
            vf_filters.append(f"crop=iw-{crop_px*2}:ih-{crop_px*2}:{crop_px}:{crop_px}")
            self.log_message.emit(f"  📐 Pixel shift: crop {crop_px}px edges")

        # Flip slight (horizontal mirror with very slight angle)
        if "flip_slight" in techniques:
            # Rotate 0.5 degree — barely visible but changes pixels
            vf_filters.append("rotate=0.008")
            self.log_message.emit(f"  🔄 Slight rotation: 0.5°")

        # Noise
        if "noise" in techniques:
            noise_level = self._config.get("noise_level", 3)
            vf_filters.append(f"noise=alls={noise_level}:allf=t")
            self.log_message.emit(f"  🌫️ Noise: level {noise_level}")

        # Brightness jitter
        if "brightness_jitter" in techniques:
            jitter = random.uniform(-0.02, 0.02)
            vf_filters.append(f"eq=brightness={jitter:.4f}")
            self.log_message.emit(f"  💡 Brightness: {jitter:+.3f}")

        # Speed tweak
        if "speed_tweak" in techniques:
            speed_min, speed_max = self._config.get("speed_range", (1.01, 1.03))
            speed = random.uniform(speed_min, speed_max)
            vf_filters.append(f"setpts={1/speed:.6f}*PTS")
            af_filters.append(f"atempo={speed:.6f}")
            self.log_message.emit(f"  ⚡ Speed tweak: {speed:.4f}x")

        # Audio pitch shift
        if "audio_pitch" in techniques:
            # Shift pitch by ±0.5% using asetrate
            pitch_shift = random.uniform(-0.005, 0.005)
            new_rate = int(44100 * (1 + pitch_shift))
            af_filters.append(f"asetrate={new_rate},aresample=44100")
            self.log_message.emit(f"  🎵 Pitch shift: {pitch_shift*100:+.2f}%")

        # Build FFmpeg command
        ar_path = os.path.join(output_dir, "antireup.mp4")
        args = ["-i", current]

        if vf_filters:
            args += ["-vf", ",".join(vf_filters)]
        if af_filters:
            args += ["-af", ",".join(af_filters)]

        args += [
            "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.2",
            "-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "17",
            "-bf", "2", "-g", "60",
        ]
        args += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]

        # Strip metadata
        if "strip_metadata" in techniques:
            args += ["-map_metadata", "-1", "-fflags", "+bitexact"]
            self.log_message.emit(f"  🗑️ Metadata stripped")

        # MD5 change (add random metadata comment to change file hash)
        if "md5_change" in techniques:
            random_id = f"vid_{random.randint(100000, 999999)}_{random.randint(1000, 9999)}"
            args += ["-metadata", f"comment={random_id}"]
            self.log_message.emit(f"  🔀 MD5 changed: {random_id}")

        args += ["-y", ar_path]
        run_ffmpeg(args)

        return ar_path

    def _split_video(self, input_path: str, output_dir: str, max_duration: int) -> list:
        """Split video into parts by duration."""
        from engine.modules.ffmpeg_utils import run_ffmpeg, get_video_info

        parts_dir = os.path.join(output_dir, "parts")
        os.makedirs(parts_dir, exist_ok=True)

        # Get video duration
        try:
            duration = get_video_info(input_path).duration
        except Exception:
            duration = 0

        if duration <= 0 or duration <= max_duration:
            return [input_path]

        # Split using FFmpeg segment
        pattern = os.path.join(parts_dir, "part_%03d.mp4")
        run_ffmpeg([
            "-i", input_path,
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(max_duration),
            "-reset_timestamps", "1",
            "-y", pattern,
        ])

        # Collect parts
        parts = sorted([
            os.path.join(parts_dir, f) for f in os.listdir(parts_dir)
            if f.startswith("part_") and f.endswith(".mp4")
        ])

        return parts if parts else [input_path]
