"""
Video Reup Studio - FFmpeg Utilities
Wrapper module for FFmpeg operations: probe, extract, encode, filters.
"""

import subprocess
import json
import os
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class VideoInfo:
    """Video file metadata."""
    path: str
    duration: float  # seconds
    width: int
    height: int
    fps: float
    codec: str
    audio_codec: str
    audio_sample_rate: int
    bitrate: int  # kbps
    size_mb: float

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def aspect_ratio(self) -> str:
        if self.width > self.height:
            return "landscape"
        elif self.width < self.height:
            return "portrait"
        return "square"

    @property
    def duration_str(self) -> str:
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"


def find_ffmpeg() -> str:
    """Find ffmpeg binary path. Project-local first, then system PATH."""
    # 1. Check project-local ffmpeg_bin folder FIRST
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local_ffmpeg = os.path.join(project_root, "ffmpeg_bin", "ffmpeg.exe")
    if os.path.isfile(local_ffmpeg):
        return local_ffmpeg
    # 2. System PATH
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    # 3. Try imageio_ffmpeg (bundled with moviepy)
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        if os.path.isfile(ffmpeg_path):
            return ffmpeg_path
    except ImportError:
        pass
    # Common Windows paths
    common_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        os.path.expanduser("~/ffmpeg/bin/ffmpeg.exe"),
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("FFmpeg not found. Install FFmpeg and add to PATH.")


def find_ffprobe() -> str:
    """Find ffprobe binary path."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        return ffprobe
    # Try same directory as ffmpeg
    try:
        ffmpeg_path = find_ffmpeg()
        ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
        if os.path.isfile(ffprobe_path):
            return ffprobe_path
    except FileNotFoundError:
        pass
    # Check project-local ffmpeg_bin folder
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    local_ffprobe = os.path.join(project_root, "ffmpeg_bin", "ffprobe.exe")
    if os.path.isfile(local_ffprobe):
        return local_ffprobe
    # imageio_ffmpeg doesn't bundle ffprobe, so download it
    try:
        import imageio_ffmpeg
        ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
        # ffprobe may not exist, fall back to ffmpeg with probe args
        for name in ["ffprobe.exe", "ffprobe"]:
            p = os.path.join(ffmpeg_dir, name)
            if os.path.isfile(p):
                return p
    except ImportError:
        pass
    raise FileNotFoundError("FFprobe not found.")


def run_ffmpeg(args: list[str], capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run ffmpeg command with error handling."""
    cmd = [find_ffmpeg()] + args
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
        timeout=3600,  # 1 hour max
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {result.stderr[:500]}")
    return result


def run_ffprobe(args: list[str]) -> dict:
    """Run ffprobe and return JSON output."""
    cmd = [find_ffprobe()] + ["-v", "quiet", "-print_format", "json"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"FFprobe error: {result.stderr[:500]}")
    return json.loads(result.stdout)


def get_video_info(video_path: str) -> VideoInfo:
    """Get comprehensive video file information."""
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    data = run_ffprobe(["-show_format", "-show_streams", video_path])

    # Find video stream
    video_stream = None
    audio_stream = None
    for stream in data.get("streams", []):
        if stream["codec_type"] == "video" and not video_stream:
            video_stream = stream
        elif stream["codec_type"] == "audio" and not audio_stream:
            audio_stream = stream

    if not video_stream:
        raise ValueError(f"No video stream found in: {video_path}")

    fmt = data.get("format", {})

    # Parse FPS from r_frame_rate (e.g., "30000/1001")
    fps_str = video_stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den) if float(den) != 0 else 30.0
    else:
        fps = float(fps_str)

    return VideoInfo(
        path=video_path,
        duration=float(fmt.get("duration", 0)),
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        fps=round(fps, 2),
        codec=video_stream.get("codec_name", "unknown"),
        audio_codec=audio_stream.get("codec_name", "none") if audio_stream else "none",
        audio_sample_rate=int(audio_stream.get("sample_rate", 0)) if audio_stream else 0,
        bitrate=int(fmt.get("bit_rate", 0)) // 1000,
        size_mb=round(os.path.getsize(video_path) / (1024 * 1024), 2),
    )


def extract_audio(video_path: str, output_path: str, sample_rate: int = 16000) -> str:
    """Extract audio from video as WAV (mono, 16kHz for Whisper)."""
    run_ffmpeg([
        "-i", video_path,
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # WAV format
        "-ar", str(sample_rate),  # sample rate
        "-ac", "1",               # mono
        "-y",                     # overwrite
        output_path,
    ])
    return output_path


def extract_audio_mp3(video_path: str, output_path: str, bitrate: str = "192k") -> str:
    """Extract audio as MP3."""
    run_ffmpeg([
        "-i", video_path,
        "-vn",
        "-acodec", "libmp3lame",
        "-b:a", bitrate,
        "-y",
        output_path,
    ])
    return output_path


def strip_metadata(video_path: str, output_path: str) -> str:
    """Remove all metadata from video."""
    run_ffmpeg([
        "-i", video_path,
        "-map_metadata", "-1",   # strip all metadata
        "-c", "copy",            # no re-encode (fast)
        "-y",
        output_path,
    ])
    return output_path


def reencode_video(
    video_path: str,
    output_path: str,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    crf: int = 23,
    preset: str = "medium",
    resolution: Optional[tuple[int, int]] = None,
) -> str:
    """Re-encode video with specified parameters."""
    args = ["-i", video_path]

    # Video filter for resolution
    if resolution:
        w, h = resolution
        args += ["-vf", f"scale={w}:{h}"]

    args += [
        "-c:v", video_codec,
        "-crf", str(crf),
        "-preset", preset,
        "-c:a", audio_codec,
        "-b:a", "128k",
        "-y",
        output_path,
    ]
    run_ffmpeg(args)
    return output_path


def add_audio_to_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    replace_audio: bool = False,
    audio_volume: float = 1.0,
    original_volume: float = 0.1,
) -> str:
    """Add audio track to video. Can replace or mix with original."""
    if replace_audio:
        # Replace original audio entirely
        run_ffmpeg([
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-y",
            output_path,
        ])
    else:
        # Mix: original (low volume) + new audio (full volume)
        run_ffmpeg([
            "-i", video_path,
            "-i", audio_path,
            "-filter_complex",
            f"[0:a]volume={original_volume}[a0];[1:a]volume={audio_volume}[a1];[a0][a1]amix=inputs=2:duration=first[aout]",
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy",
            "-y",
            output_path,
        ])
    return output_path


def burn_subtitle(video_path: str, subtitle_path: str, output_path: str) -> str:
    """Burn ASS/SRT subtitle into video (hardcoded)."""
    # Escape path for FFmpeg filter (Windows backslashes)
    sub_escaped = subtitle_path.replace("\\", "/").replace(":", "\\:")

    run_ffmpeg([
        "-i", video_path,
        "-vf", f"ass={sub_escaped}" if subtitle_path.endswith(".ass") else f"subtitles={sub_escaped}",
        "-c:a", "copy",
        "-y",
        output_path,
    ])
    return output_path


def cut_video(video_path: str, output_path: str, start: float, end: float) -> str:
    """Cut video segment by timestamp (seconds)."""
    duration = end - start
    run_ffmpeg([
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
        "-c", "copy",          # no re-encode (fast)
        "-avoid_negative_ts", "make_zero",
        "-y",
        output_path,
    ])
    return output_path


def concat_videos(video_paths: list[str], output_path: str) -> str:
    """Concatenate multiple videos into one."""
    # Create concat file
    concat_file = output_path + ".concat.txt"
    with open(concat_file, "w") as f:
        for vp in video_paths:
            f.write(f"file '{vp}'\n")

    run_ffmpeg([
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        "-y",
        output_path,
    ])

    # Cleanup
    os.remove(concat_file)
    return output_path


def add_logo(
    video_path: str,
    logo_path: str,
    output_path: str,
    position: str = "top-right",
    opacity: float = 0.8,
    scale: float = 0.1,
) -> str:
    """Add logo/watermark overlay to video."""
    # Position mapping
    positions = {
        "top-left": "10:10",
        "top-right": "W-w-10:10",
        "bottom-left": "10:H-h-10",
        "bottom-right": "W-w-10:H-h-10",
        "center": "(W-w)/2:(H-h)/2",
    }
    pos = positions.get(position, positions["top-right"])

    run_ffmpeg([
        "-i", video_path,
        "-i", logo_path,
        "-filter_complex",
        f"[1:v]scale=iw*{scale}:-1,format=rgba,colorchannelmixer=aa={opacity}[logo];[0:v][logo]overlay={pos}[out]",
        "-map", "[out]",
        "-map", "0:a?",
        "-c:a", "copy",
        "-y",
        output_path,
    ])
    return output_path


def apply_visual_filters(
    video_path: str,
    output_path: str,
    crop_percent: float = 0.03,
    hue_shift: float = 5.0,
    brightness: float = 0.03,
    speed: float = 1.02,
    mirror: bool = False,
    pitch_shift: float = 0.5,
) -> str:
    """Apply anti-reup visual/audio filters."""
    filters = []

    # Crop (zoom in slightly)
    if crop_percent > 0:
        cp = crop_percent
        filters.append(f"crop=iw*(1-{cp}):ih*(1-{cp}):iw*{cp/2}:ih*{cp/2}")
        filters.append("scale=iw:ih")  # scale back to original size

    # Mirror
    if mirror:
        filters.append("hflip")

    # Hue shift
    if hue_shift != 0:
        filters.append(f"hue=h={hue_shift}")

    # Brightness
    if brightness != 0:
        filters.append(f"eq=brightness={brightness}")

    # Speed
    video_filter = ",".join(filters) if filters else None
    audio_filters = []

    if speed != 1.0:
        if video_filter:
            video_filter += f",setpts={1/speed}*PTS"
        else:
            video_filter = f"setpts={1/speed}*PTS"
        audio_filters.append(f"atempo={speed}")

    # Pitch shift (via asetrate + aresample)
    if pitch_shift != 0:
        # Shift pitch by changing sample rate then resampling
        factor = 2 ** (pitch_shift / 12)  # semitones to factor
        audio_filters.append(f"asetrate=44100*{factor},aresample=44100")

    args = ["-i", video_path]

    filter_complex_parts = []
    if video_filter:
        filter_complex_parts.append(f"[0:v]{video_filter}[vout]")
    if audio_filters:
        af = ",".join(audio_filters)
        filter_complex_parts.append(f"[0:a]{af}[aout]")

    if filter_complex_parts:
        args += ["-filter_complex", ";".join(filter_complex_parts)]
        if video_filter:
            args += ["-map", "[vout]"]
        else:
            args += ["-map", "0:v"]
        if audio_filters:
            args += ["-map", "[aout]"]
        else:
            args += ["-map", "0:a"]
    else:
        args += ["-c", "copy"]

    args += [
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "medium",
        "-c:a", "aac",
        "-y",
        output_path,
    ]

    run_ffmpeg(args)
    return output_path


def detect_silence(video_path: str, threshold: float = -30, min_duration: float = 0.5) -> list[dict]:
    """Detect silence periods in video (for smart splitting)."""
    cmd = [find_ffmpeg()] + [
        "-i", video_path,
        "-af", f"silencedetect=noise={threshold}dB:d={min_duration}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    silences = []
    lines = result.stderr.split("\n")
    current = {}
    for line in lines:
        if "silence_start:" in line:
            try:
                current["start"] = float(line.split("silence_start:")[1].strip().split()[0])
            except (IndexError, ValueError):
                pass
        elif "silence_end:" in line:
            try:
                parts = line.split("silence_end:")[1].strip().split()
                current["end"] = float(parts[0])
                if "start" in current:
                    silences.append(current)
                current = {}
            except (IndexError, ValueError):
                current = {}

    return silences


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        info = get_video_info(sys.argv[1])
        print(f"File: {info.path}")
        print(f"Duration: {info.duration_str} ({info.duration:.1f}s)")
        print(f"Resolution: {info.resolution} ({info.aspect_ratio})")
        print(f"FPS: {info.fps}")
        print(f"Codec: {info.codec} / {info.audio_codec}")
        print(f"Bitrate: {info.bitrate} kbps")
        print(f"Size: {info.size_mb} MB")
    else:
        print("Usage: python ffmpeg_utils.py <video_path>")
