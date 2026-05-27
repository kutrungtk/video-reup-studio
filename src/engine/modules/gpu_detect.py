"""
GPU Detection — Auto-detect hardware encoder for FFmpeg.
Priority: NVIDIA NVENC → AMD AMF → Intel QSV → CPU (libx264)
"""

import subprocess
import shutil
import os


# Cache result — detect once per session
_cached_encoder = None


def detect_gpu_encoder(ffmpeg_path: str = None) -> dict:
    """
    Detect best available hardware encoder.
    Returns dict with encoder config for FFmpeg.
    """
    global _cached_encoder
    if _cached_encoder is not None:
        return _cached_encoder

    if not ffmpeg_path:
        # Try project-local first
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        local_ffmpeg = os.path.join(project_root, "ffmpeg_bin", "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            ffmpeg_path = local_ffmpeg
        else:
            ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"

    # Test encoders in priority order
    encoders = [
        {
            "name": "NVIDIA NVENC",
            "icon": "🟢",
            "codec": "h264_nvenc",
            "params": ["-preset", "p4", "-rc", "vbr", "-cq", "18", "-profile:v", "high"],
            "test_args": ["-f", "lavfi", "-i", "nullsrc=s=64x64:d=1", "-c:v", "h264_nvenc", "-f", "null", "-"],
        },
        {
            "name": "AMD AMF",
            "icon": "🔴",
            "codec": "h264_amf",
            "params": ["-quality", "quality", "-rc", "vbr_peak", "-profile:v", "high"],
            "test_args": ["-f", "lavfi", "-i", "nullsrc=s=64x64:d=1", "-c:v", "h264_amf", "-f", "null", "-"],
        },
        {
            "name": "Intel QSV",
            "icon": "🔵",
            "codec": "h264_qsv",
            "params": ["-preset", "medium", "-global_quality", "18", "-profile:v", "high"],
            "test_args": ["-f", "lavfi", "-i", "nullsrc=s=64x64:d=1", "-c:v", "h264_qsv", "-f", "null", "-"],
        },
    ]

    for enc in encoders:
        try:
            cmd = [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error"] + enc["test_args"]
            result = subprocess.run(
                cmd, capture_output=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                _cached_encoder = {
                    "name": enc["name"],
                    "icon": enc["icon"],
                    "codec": enc["codec"],
                    "is_gpu": True,
                    "encode_params": _build_gpu_params(enc),
                }
                return _cached_encoder
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            continue

    # Fallback: CPU libx264
    _cached_encoder = {
        "name": "CPU (libx264)",
        "icon": "💻",
        "codec": "libx264",
        "is_gpu": False,
        "encode_params": _build_cpu_params(),
    }
    return _cached_encoder


def _build_gpu_params(enc: dict) -> list:
    """Build FFmpeg encode params for GPU encoder."""
    codec = enc["codec"]

    if codec == "h264_nvenc":
        # NVENC: -cq for quality (like CRF), -preset p4 = balanced
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-rc", "vbr",
            "-cq", "18",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-bf", "2",
            "-g", "60",
            "-movflags", "+faststart",
        ]
    elif codec == "h264_amf":
        return [
            "-c:v", "h264_amf",
            "-quality", "quality",
            "-rc", "vbr_peak",
            "-qp_i", "18", "-qp_p", "20", "-qp_b", "22",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-bf", "2",
            "-g", "60",
            "-movflags", "+faststart",
        ]
    elif codec == "h264_qsv":
        return [
            "-c:v", "h264_qsv",
            "-preset", "medium",
            "-global_quality", "18",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-bf", "2",
            "-g", "60",
            "-movflags", "+faststart",
        ]
    return _build_cpu_params()


def _build_cpu_params() -> list:
    """Build FFmpeg encode params for CPU (libx264)."""
    return [
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "medium",
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-bf", "2",
        "-g", "60",
        "-movflags", "+faststart",
    ]


def get_encode_command(quality_key: str = "fullhd", ffmpeg_path: str = None) -> list:
    """
    Get full encode params (codec + quality + maxrate).
    Combines GPU detection with quality preset.
    """
    from config.constants import QUALITY_PRESETS

    quality = QUALITY_PRESETS.get(quality_key, QUALITY_PRESETS["fullhd"])
    encoder = detect_gpu_encoder(ffmpeg_path)

    if encoder["is_gpu"]:
        # GPU: use hardware params + add maxrate/bufsize
        params = list(encoder["encode_params"])
        params += ["-maxrate", quality["maxrate"], "-bufsize", quality["bufsize"]]
    else:
        # CPU: CRF + maxrate + bufsize
        params = [
            "-c:v", "libx264",
            "-crf", str(quality["crf"]),
            "-maxrate", quality["maxrate"],
            "-bufsize", quality["bufsize"],
            "-preset", "medium",
            "-profile:v", "high",
            "-level:v", quality["level"],
            "-pix_fmt", "yuv420p",
            "-bf", "2",
            "-g", "60",
            "-movflags", "+faststart",
        ]

    return params
