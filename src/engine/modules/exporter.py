"""
Video Reup Studio - Exporter Module
Export video with platform-specific presets + logo overlay.
"""

import json
import os
from pathlib import Path
from typing import Optional

from engine.modules.ffmpeg_utils import run_ffmpeg, get_video_info, add_logo


# Platform export presets
PLATFORM_PRESETS = {
    "tiktok": {
        "name": "TikTok",
        "width": 1080,
        "height": 1920,
        "aspect": "9:16",
        "max_duration": 180,  # 3 minutes
        "max_size_mb": 287,
        "codec": "libx264",
        "audio_codec": "aac",
        "crf": 23,
        "preset": "medium",
        "audio_bitrate": "128k",
        "fps": 30,
        "pixel_format": "yuv420p",
    },
    "facebook": {
        "name": "Facebook",
        "width": 1920,
        "height": 1080,
        "aspect": "16:9",
        "max_duration": 14400,  # 240 minutes
        "max_size_mb": 4096,
        "codec": "libx264",
        "audio_codec": "aac",
        "crf": 22,
        "preset": "medium",
        "audio_bitrate": "192k",
        "fps": 30,
        "pixel_format": "yuv420p",
    },
    "facebook_square": {
        "name": "Facebook (Square)",
        "width": 1080,
        "height": 1080,
        "aspect": "1:1",
        "max_duration": 14400,
        "max_size_mb": 4096,
        "codec": "libx264",
        "audio_codec": "aac",
        "crf": 22,
        "preset": "medium",
        "audio_bitrate": "192k",
        "fps": 30,
        "pixel_format": "yuv420p",
    },
    "youtube": {
        "name": "YouTube",
        "width": 1920,
        "height": 1080,
        "aspect": "16:9",
        "max_duration": 43200,  # 12 hours
        "max_size_mb": 128000,
        "codec": "libx264",
        "audio_codec": "aac",
        "crf": 20,
        "preset": "slow",
        "audio_bitrate": "256k",
        "fps": 30,
        "pixel_format": "yuv420p",
    },
    "youtube_shorts": {
        "name": "YouTube Shorts",
        "width": 1080,
        "height": 1920,
        "aspect": "9:16",
        "max_duration": 60,
        "max_size_mb": 4096,
        "codec": "libx264",
        "audio_codec": "aac",
        "crf": 22,
        "preset": "medium",
        "audio_bitrate": "192k",
        "fps": 30,
        "pixel_format": "yuv420p",
    },
    "instagram_reels": {
        "name": "Instagram Reels",
        "width": 1080,
        "height": 1920,
        "aspect": "9:16",
        "max_duration": 90,
        "max_size_mb": 250,
        "codec": "libx264",
        "audio_codec": "aac",
        "crf": 23,
        "preset": "medium",
        "audio_bitrate": "128k",
        "fps": 30,
        "pixel_format": "yuv420p",
    },
}


def export_video(
    video_path: str,
    output_path: str,
    platform: str = "tiktok",
    logo_path: Optional[str] = None,
    logo_position: str = "top-right",
    logo_opacity: float = 0.8,
    logo_scale: float = 0.08,
    custom_preset: Optional[dict] = None,
) -> dict:
    """
    Export video with platform-specific encoding.
    
    Args:
        video_path: Input video path
        output_path: Output video path
        platform: Platform preset name
        logo_path: Optional logo/watermark image path
        logo_position: Logo position (top-left, top-right, bottom-left, bottom-right)
        logo_opacity: Logo opacity (0-1)
        logo_scale: Logo scale relative to video width
        custom_preset: Override preset values
    
    Returns:
        Dict with export info: {path, size_mb, duration, resolution, platform}
    """
    preset = PLATFORM_PRESETS.get(platform, PLATFORM_PRESETS["tiktok"]).copy()
    if custom_preset:
        preset.update(custom_preset)

    print(f"[Exporter] Exporting for {preset['name']}...")
    print(f"  Target: {preset['width']}x{preset['height']} ({preset['aspect']})")

    # Get input video info
    info = get_video_info(video_path)
    input_width = info.width
    input_height = info.height

    # Build video filter for scaling/padding
    vf = _build_scale_filter(input_width, input_height, preset["width"], preset["height"])

    # Add logo if specified
    if logo_path and os.path.isfile(logo_path):
        # First export without logo, then add logo
        temp_output = output_path + ".temp.mp4"
        _encode_video(video_path, temp_output, preset, vf)
        add_logo(temp_output, logo_path, output_path, logo_position, logo_opacity, logo_scale)
        os.remove(temp_output)
    else:
        _encode_video(video_path, output_path, preset, vf)

    # Verify output
    output_info = get_video_info(output_path)
    size_mb = output_info.size_mb

    # Check size limit
    if size_mb > preset["max_size_mb"]:
        print(f"[Exporter] WARNING: Output ({size_mb:.1f}MB) exceeds platform limit ({preset['max_size_mb']}MB)")
        # Re-encode with higher CRF to reduce size
        _reduce_file_size(output_path, preset["max_size_mb"], preset)

    result = {
        "path": output_path,
        "size_mb": round(output_info.size_mb, 2),
        "duration": round(output_info.duration, 2),
        "resolution": f"{output_info.width}x{output_info.height}",
        "platform": platform,
        "codec": output_info.codec,
    }

    print(f"[Exporter] Done: {output_path}")
    print(f"  Size: {result['size_mb']} MB | Duration: {output_info.duration_str} | {result['resolution']}")

    return result


def _build_scale_filter(in_w: int, in_h: int, out_w: int, out_h: int) -> str:
    """
    Build FFmpeg scale/pad filter to fit video into target dimensions.
    Maintains aspect ratio, adds black bars if needed.
    """
    in_aspect = in_w / in_h
    out_aspect = out_w / out_h

    if abs(in_aspect - out_aspect) < 0.01:
        # Same aspect ratio, just scale
        return f"scale={out_w}:{out_h}"
    elif in_aspect > out_aspect:
        # Input is wider, scale to width and pad top/bottom
        return f"scale={out_w}:-2,pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black"
    else:
        # Input is taller, scale to height and pad left/right
        return f"scale=-2:{out_h},pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black"


def _encode_video(video_path: str, output_path: str, preset: dict, vf: str):
    """Encode video with preset parameters."""
    args = [
        "-i", video_path,
        "-vf", vf,
        "-c:v", preset["codec"],
        "-crf", str(preset["crf"]),
        "-preset", preset["preset"],
        "-c:a", preset["audio_codec"],
        "-b:a", preset["audio_bitrate"],
        "-r", str(preset["fps"]),
        "-pix_fmt", preset["pixel_format"],
        "-movflags", "+faststart",  # Web optimization
        "-y",
        output_path,
    ]

    # Duration limit
    if preset.get("max_duration"):
        info = get_video_info(video_path)
        if info.duration > preset["max_duration"]:
            args = ["-t", str(preset["max_duration"])] + args
            print(f"[Exporter] WARNING: Video truncated to {preset['max_duration']}s (platform limit)")

    run_ffmpeg(args)


def _reduce_file_size(video_path: str, max_size_mb: float, preset: dict):
    """Re-encode with higher CRF to reduce file size."""
    import shutil

    temp = video_path + ".reducing.mp4"
    shutil.move(video_path, temp)

    # Increase CRF by 3 (significant size reduction)
    new_crf = preset["crf"] + 3
    args = [
        "-i", temp,
        "-c:v", preset["codec"],
        "-crf", str(new_crf),
        "-preset", "fast",
        "-c:a", preset["audio_codec"],
        "-b:a", "96k",  # Lower audio bitrate too
        "-y",
        video_path,
    ]
    run_ffmpeg(args)
    os.remove(temp)

    new_size = os.path.getsize(video_path) / (1024 * 1024)
    print(f"[Exporter] Reduced to {new_size:.1f}MB (CRF={new_crf})")


def list_presets() -> dict:
    """Return available platform presets."""
    return {name: {"name": p["name"], "resolution": f"{p['width']}x{p['height']}", "aspect": p["aspect"]}
            for name, p in PLATFORM_PRESETS.items()}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python exporter.py <video_path> [--platform tiktok] [--logo logo.png] [--output out.mp4]")
        print("\nAvailable platforms:")
        for name, info in list_presets().items():
            print(f"  {name:20s} {info.get('aspect', '9:16')} (max {info['max_duration']}s)")
        sys.exit(1)

    video = sys.argv[1]
    platform = "tiktok"
    logo = None
    output = None

    for i, arg in enumerate(sys.argv):
        if arg == "--platform" and i + 1 < len(sys.argv):
            platform = sys.argv[i + 1]
        elif arg == "--logo" and i + 1 < len(sys.argv):
            logo = sys.argv[i + 1]
        elif arg == "--output" and i + 1 < len(sys.argv):
            output = sys.argv[i + 1]

    if not output:
        output = f"{Path(video).stem}_{platform}.mp4"

    export_video(video, output, platform=platform, logo_path=logo)
