"""
Video Reup Studio - Anti-Reup Module
Apply transformations to bypass content detection algorithms.
Techniques from: Videos_downloader (mirror, speed, color shift) + custom additions.
"""

import json
import os
import random
from typing import Optional
from dataclasses import dataclass, field

from modules.ffmpeg_utils import run_ffmpeg, strip_metadata


@dataclass
class AntiReupConfig:
    """Configuration for anti-reup effects. All toggleable."""
    # Metadata
    strip_metadata: bool = True

    # Visual
    crop_percent: float = 0.03        # Random crop 2-5%
    hue_shift: float = 5.0            # Hue rotation ±5°
    brightness_shift: float = 0.03    # Brightness ±3%
    saturation_shift: float = 0.05    # Saturation ±5%
    contrast_shift: float = 0.02      # Contrast ±2%

    # Transform
    mirror: bool = False              # Horizontal flip — DISABLED by default (spec-v2)
    speed: float = 1.02               # Speed multiplier (1.02-1.05)
    rotation: float = 0.0             # Slight rotation (0-1°)

    # Audio
    pitch_shift: float = 0.5          # Semitones ±0.5
    add_noise: bool = True            # Invisible noise layer
    noise_volume: float = 0.005       # Very low noise

    # Frame padding (spec-v2)
    frame_padding: bool = True        # Add black frames at start/end
    padding_frames: int = 2           # Number of black frames (1-3)

    # Advanced
    re_encode: bool = True            # Force re-encode (new codec params)
    randomize: bool = True            # Randomize values within ranges

    def randomize_values(self):
        """Randomize effect values within safe ranges."""
        if not self.randomize:
            return

        self.crop_percent = random.uniform(0.02, 0.05)
        self.hue_shift = random.uniform(-8, 8)
        self.brightness_shift = random.uniform(-0.04, 0.04)
        self.saturation_shift = random.uniform(-0.08, 0.08)
        self.contrast_shift = random.uniform(-0.03, 0.03)
        self.speed = random.uniform(1.01, 1.04)
        self.pitch_shift = random.uniform(-0.8, 0.8)
        self.rotation = random.uniform(-0.5, 0.5)
        self.padding_frames = random.randint(1, 3)

    @classmethod
    def from_dict(cls, data: dict) -> "AntiReupConfig":
        """Create config from dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        """Export config as dict."""
        return {
            "strip_metadata": self.strip_metadata,
            "crop_percent": self.crop_percent,
            "hue_shift": self.hue_shift,
            "brightness_shift": self.brightness_shift,
            "saturation_shift": self.saturation_shift,
            "contrast_shift": self.contrast_shift,
            "mirror": self.mirror,
            "speed": self.speed,
            "rotation": self.rotation,
            "pitch_shift": self.pitch_shift,
            "add_noise": self.add_noise,
            "noise_volume": self.noise_volume,
            "frame_padding": self.frame_padding,
            "padding_frames": self.padding_frames,
            "re_encode": self.re_encode,
            "randomize": self.randomize,
        }


def apply_anti_reup(
    video_path: str,
    output_path: str,
    config: Optional[AntiReupConfig] = None,
) -> str:
    """
    Apply anti-reup transformations to video.
    
    Args:
        video_path: Input video path
        output_path: Output video path
        config: AntiReupConfig (None = use defaults with randomization)
    
    Returns:
        Path to processed video
    """
    if config is None:
        config = AntiReupConfig()

    # Randomize values for uniqueness
    if config.randomize:
        config.randomize_values()

    print(f"[Anti-Reup] Applying effects...")
    print(f"  Crop: {config.crop_percent:.3f}")
    print(f"  Hue: {config.hue_shift:.1f}°")
    print(f"  Brightness: {config.brightness_shift:.3f}")
    print(f"  Speed: {config.speed:.3f}x")
    print(f"  Mirror: {config.mirror}")
    print(f"  Pitch: {config.pitch_shift:.2f} semitones")
    print(f"  Frame padding: {config.padding_frames} frames")

    # Build video filters
    vfilters = []
    afilters = []

    # 0. Frame padding at START (black frames)
    if config.frame_padding and config.padding_frames > 0:
        # tpad: add black frames at start and end
        fps = 30  # assume 30fps, each frame = 1/30s
        pad_dur = config.padding_frames / fps
        vfilters.append(f"tpad=start_duration={pad_dur:.4f}:start_mode=add:color=black:stop_duration={pad_dur:.4f}:stop_mode=add")

    # 1. Crop (zoom in slightly to change frame hash)
    if config.crop_percent > 0:
        cp = config.crop_percent
        vfilters.append(f"crop=iw*(1-{cp:.4f}):ih*(1-{cp:.4f}):iw*{cp/2:.4f}:ih*{cp/2:.4f}")
        vfilters.append("scale=iw:ih:flags=lanczos")  # Scale back

    # 2. Mirror (horizontal flip)
    if config.mirror:
        vfilters.append("hflip")

    # 3. Color adjustments
    eq_parts = []
    if config.brightness_shift != 0:
        eq_parts.append(f"brightness={config.brightness_shift:.4f}")
    if config.saturation_shift != 0:
        sat = 1.0 + config.saturation_shift
        eq_parts.append(f"saturation={sat:.4f}")
    if config.contrast_shift != 0:
        con = 1.0 + config.contrast_shift
        eq_parts.append(f"contrast={con:.4f}")
    if eq_parts:
        vfilters.append(f"eq={':'.join(eq_parts)}")

    # 4. Hue shift
    if config.hue_shift != 0:
        vfilters.append(f"hue=h={config.hue_shift:.2f}")

    # 5. Slight rotation (changes pixel positions)
    if config.rotation != 0:
        angle = config.rotation * 3.14159 / 180  # degrees to radians
        vfilters.append(f"rotate={angle:.6f}:fillcolor=black@0")

    # 6. Speed adjustment
    if config.speed != 1.0:
        vfilters.append(f"setpts={1/config.speed:.6f}*PTS")
        afilters.append(f"atempo={config.speed:.4f}")

    # 7. Audio pitch shift
    if config.pitch_shift != 0:
        factor = 2 ** (config.pitch_shift / 12)
        afilters.append(f"asetrate=44100*{factor:.6f}")
        afilters.append("aresample=44100")

    # 8. Add noise layer (invisible but changes audio hash)
    if config.add_noise:
        noise_vol = config.noise_volume
        afilters.append(
            f"aeval='val(0)+random(0)*{noise_vol:.6f}':c=same"
        )

    # Build FFmpeg command
    args = ["-i", video_path]

    # Build filter complex
    filter_parts = []
    if vfilters:
        vf = ",".join(vfilters)
        filter_parts.append(f"[0:v]{vf}[vout]")
    if afilters:
        af = ",".join(afilters)
        filter_parts.append(f"[0:a]{af}[aout]")

    if filter_parts:
        args += ["-filter_complex", ";".join(filter_parts)]
        args += ["-map", "[vout]" if vfilters else "0:v"]
        args += ["-map", "[aout]" if afilters else "0:a"]

    # Encoding params (slightly different from source to change binary)
    if config.re_encode:
        # Randomize CRF slightly for different output
        crf = random.randint(20, 24)
        args += [
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "medium",
            "-profile:v", "high",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
        ]
    else:
        args += ["-c:v", "copy", "-c:a", "copy"]

    # Strip metadata
    if config.strip_metadata:
        args += ["-map_metadata", "-1"]

    # Remove chapters, data streams
    args += [
        "-map_chapters", "-1",
        "-fflags", "+bitexact",
        "-flags:v", "+bitexact",
        "-flags:a", "+bitexact",
        "-y",
        output_path,
    ]

    run_ffmpeg(args)

    # Verify output is different from input
    input_size = os.path.getsize(video_path)
    output_size = os.path.getsize(output_path)
    if input_size == output_size:
        print("[Anti-Reup] WARNING: Output size identical to input. Effects may not have applied.")

    print(f"[Anti-Reup] Done: {output_path}")
    print(f"  Input size: {input_size / 1024 / 1024:.1f} MB")
    print(f"  Output size: {output_size / 1024 / 1024:.1f} MB")

    return output_path


def get_preset(name: str) -> AntiReupConfig:
    """Get predefined anti-reup presets."""
    presets = {
        "light": AntiReupConfig(
            crop_percent=0.02,
            hue_shift=3.0,
            brightness_shift=0.02,
            speed=1.01,
            mirror=False,
            pitch_shift=0.3,
            add_noise=True,
            frame_padding=True,
            padding_frames=1,
            randomize=False,
        ),
        "medium": AntiReupConfig(
            crop_percent=0.04,
            hue_shift=6.0,
            brightness_shift=0.04,
            speed=1.03,
            mirror=False,
            pitch_shift=0.5,
            add_noise=True,
            frame_padding=True,
            padding_frames=2,
            randomize=True,
        ),
        "heavy": AntiReupConfig(
            crop_percent=0.06,
            hue_shift=10.0,
            brightness_shift=0.05,
            speed=1.05,
            mirror=False,  # spec-v2: NEVER flip
            pitch_shift=0.8,
            add_noise=True,
            frame_padding=True,
            padding_frames=3,
            randomize=True,
        ),
        "tiktok": AntiReupConfig(
            crop_percent=0.03,
            hue_shift=5.0,
            brightness_shift=0.03,
            speed=1.02,
            mirror=False,
            pitch_shift=0.4,
            add_noise=True,
            frame_padding=True,
            padding_frames=2,
            randomize=True,
        ),
        "youtube": AntiReupConfig(
            crop_percent=0.02,
            hue_shift=4.0,
            brightness_shift=0.02,
            speed=1.01,
            mirror=False,
            pitch_shift=0.3,
            add_noise=True,
            frame_padding=True,
            padding_frames=1,
            randomize=True,
        ),
    }
    return presets.get(name, presets["medium"])


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python anti_reup.py <video_path> [--preset medium] [--mirror] [--output out.mp4]")
        print("Presets: light, medium, heavy, tiktok, youtube")
        sys.exit(1)

    video = sys.argv[1]
    preset_name = "medium"
    output = None
    mirror = False

    for i, arg in enumerate(sys.argv):
        if arg == "--preset" and i + 1 < len(sys.argv):
            preset_name = sys.argv[i + 1]
        elif arg == "--output" and i + 1 < len(sys.argv):
            output = sys.argv[i + 1]
        elif arg == "--mirror":
            mirror = True

    config = get_preset(preset_name)
    if mirror:
        config.mirror = True

    if not output:
        stem = Path(video).stem
        output = f"{stem}_antireup.mp4"

    apply_anti_reup(video, output, config)
