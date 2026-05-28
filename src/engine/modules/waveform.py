"""
Video Reup Studio - Waveform Generator
Generate audio waveform data for timeline visualization.
Outputs JSON array of amplitude values for GUI to render.
"""

import json
import os
import struct
import subprocess
from typing import Optional

from engine.modules.ffmpeg_utils import find_ffmpeg


def generate_waveform(
    audio_path: str,
    output_json: str,
    samples: int = 800,
    channel: int = 0,
) -> str:
    """
    Generate waveform amplitude data from audio/video file.
    
    Extracts audio, downsamples to `samples` points, normalizes to 0.0-1.0.
    Output is a JSON file with array of float values.
    
    Args:
        audio_path: Path to audio or video file
        output_json: Path to save waveform JSON
        samples: Number of amplitude samples (width of waveform display)
        channel: Audio channel to analyze (0 = left/mono)
    
    Returns:
        Path to output JSON file
    """
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Extract raw PCM audio via FFmpeg
    temp_pcm = output_json + ".raw"

    try:
        ffmpeg = find_ffmpeg()
        cmd = [
            ffmpeg,
            "-i", audio_path,
            "-vn",                    # no video
            "-ac", "1",               # mono
            "-ar", "8000",            # low sample rate (enough for waveform)
            "-f", "s16le",            # raw 16-bit signed PCM
            "-y",
            temp_pcm,
        ]
        subprocess.run(cmd, capture_output=True, timeout=60)

        if not os.path.isfile(temp_pcm) or os.path.getsize(temp_pcm) == 0:
            # Fallback: generate empty waveform
            waveform = [0.0] * samples
        else:
            # Read raw PCM data
            with open(temp_pcm, "rb") as f:
                raw_data = f.read()

            # Parse 16-bit samples
            num_samples = len(raw_data) // 2
            pcm_samples = struct.unpack(f"<{num_samples}h", raw_data[:num_samples * 2])

            # Downsample to target number of points
            waveform = _downsample(pcm_samples, samples)

    finally:
        # Cleanup temp file
        if os.path.exists(temp_pcm):
            os.remove(temp_pcm)

    # Save as JSON
    os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)
    with open(output_json, "w") as f:
        json.dump({"samples": waveform, "count": len(waveform)}, f)

    return output_json


def _downsample(pcm_samples: tuple, target_count: int) -> list[float]:
    """
    Downsample PCM data to target number of amplitude points.
    Uses peak amplitude per bucket, normalized to 0.0-1.0.
    """
    total = len(pcm_samples)
    if total == 0:
        return [0.0] * target_count

    bucket_size = max(1, total // target_count)
    waveform = []

    for i in range(target_count):
        start = i * bucket_size
        end = min(start + bucket_size, total)
        if start >= total:
            waveform.append(0.0)
            continue

        # Peak amplitude in this bucket
        bucket = pcm_samples[start:end]
        peak = max(abs(min(bucket)), abs(max(bucket)))
        waveform.append(peak)

    # Normalize to 0.0 - 1.0
    max_val = max(waveform) if waveform else 1
    if max_val > 0:
        waveform = [v / max_val for v in waveform]

    return waveform


def generate_waveform_for_segments(
    segments: list,
    output_dir: str,
    samples_per_second: int = 20,
) -> dict:
    """
    Generate waveform data for each audio segment.
    Returns dict mapping segment index to waveform data.
    
    Args:
        segments: List of Segment objects with voice_path
        output_dir: Directory to save waveform JSONs
        samples_per_second: Resolution of waveform
    
    Returns:
        Dict {segment_index: [amplitude_values]}
    """
    os.makedirs(output_dir, exist_ok=True)
    waveforms = {}

    for seg in segments:
        if not seg.voice_path or not os.path.isfile(seg.voice_path):
            continue

        # Calculate samples based on duration
        num_samples = max(10, int(seg.duration * samples_per_second))
        json_path = os.path.join(output_dir, f"waveform_{seg.index:03d}.json")

        try:
            generate_waveform(seg.voice_path, json_path, samples=num_samples)
            with open(json_path, "r") as f:
                data = json.load(f)
            waveforms[seg.index] = data["samples"]
        except Exception as e:
            print(f"[Waveform] Warning: failed for segment {seg.index}: {e}")
            waveforms[seg.index] = [0.0] * num_samples

    return waveforms


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python waveform.py <audio_or_video_path> [output.json] [samples]")
        sys.exit(1)

    audio = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "waveform.json"
    n_samples = int(sys.argv[3]) if len(sys.argv) > 3 else 800

    generate_waveform(audio, output, samples=n_samples)
    print(f"Waveform saved: {output} ({n_samples} samples)")
