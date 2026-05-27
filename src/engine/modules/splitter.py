"""
Video Reup Studio - Smart Splitter Module
Split long videos into parts with intelligent cut points.
Avoids cutting mid-sentence using transcript timestamps and silence detection.
"""

import json
import os
from pathlib import Path
from typing import Optional

from modules.ffmpeg_utils import cut_video, detect_silence, get_video_info


def smart_split(
    video_path: str,
    output_dir: str,
    target_duration: float = 60.0,
    transcript_data: Optional[dict] = None,
    min_duration: float = 15.0,
    max_deviation: float = 10.0,
    fade_duration: float = 0.0,
    output_prefix: str = "part",
) -> list[dict]:
    """
    Split video into parts at intelligent cut points.
    
    Priority for finding cut points:
    1. Sentence boundaries (from transcript)
    2. Silence gaps
    3. Exact duration (fallback)
    
    Args:
        video_path: Input video path
        output_dir: Directory for output parts
        target_duration: Target duration per part (seconds)
        transcript_data: Transcript dict (for sentence boundaries)
        min_duration: Minimum part duration (seconds)
        max_deviation: Max seconds to deviate from target for better cut point
        fade_duration: Fade in/out duration (0 = no fade)
        output_prefix: Filename prefix for parts
    
    Returns:
        List of dicts with part info: {path, start, end, duration, index}
    """
    os.makedirs(output_dir, exist_ok=True)

    video_info = get_video_info(video_path)
    total_duration = video_info.duration

    print(f"[Splitter] Video: {video_info.duration_str} ({total_duration:.1f}s)")
    print(f"[Splitter] Target: {target_duration}s per part")

    # If video is shorter than target, no split needed
    if total_duration <= target_duration + max_deviation:
        print("[Splitter] Video shorter than target duration, no split needed.")
        # Just copy to output
        output_path = os.path.join(output_dir, f"{output_prefix}_001.mp4")
        cut_video(video_path, output_path, 0, total_duration)
        return [{"path": output_path, "start": 0, "end": total_duration, "duration": total_duration, "index": 1}]

    # Find optimal cut points
    cut_points = _find_cut_points(
        total_duration=total_duration,
        target_duration=target_duration,
        transcript_data=transcript_data,
        video_path=video_path,
        max_deviation=max_deviation,
        min_duration=min_duration,
    )

    print(f"[Splitter] Found {len(cut_points) + 1} parts")

    # Execute cuts
    parts = []
    cut_starts = [0.0] + cut_points
    cut_ends = cut_points + [total_duration]

    for i, (start, end) in enumerate(zip(cut_starts, cut_ends)):
        index = i + 1
        duration = end - start

        if duration < min_duration / 2:
            # Skip very short segments
            continue

        output_path = os.path.join(output_dir, f"{output_prefix}_{index:03d}.mp4")

        if fade_duration > 0:
            _cut_with_fade(video_path, output_path, start, end, fade_duration)
        else:
            cut_video(video_path, output_path, start, end)

        parts.append({
            "path": output_path,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(duration, 3),
            "index": index,
        })

        print(f"  Part {index}: {_format_time(start)} → {_format_time(end)} ({duration:.1f}s)")

    print(f"[Splitter] Done: {len(parts)} parts created in {output_dir}")
    return parts


def _find_cut_points(
    total_duration: float,
    target_duration: float,
    transcript_data: Optional[dict],
    video_path: str,
    max_deviation: float,
    min_duration: float,
) -> list[float]:
    """Find optimal cut points using transcript and silence detection."""

    # Calculate approximate number of cuts needed
    num_parts = max(1, round(total_duration / target_duration))
    if num_parts <= 1:
        return []

    # Get candidate cut points
    candidates = []

    # Priority 1: Sentence boundaries from transcript
    if transcript_data and transcript_data.get("segments"):
        segments = transcript_data["segments"]
        for seg in segments:
            # End of each sentence is a good cut point
            candidates.append({
                "time": seg["end"],
                "priority": 1,
                "type": "sentence",
            })

    # Priority 2: Silence gaps
    try:
        silences = detect_silence(video_path, threshold=-35, min_duration=0.3)
        for silence in silences:
            # Middle of silence is ideal cut point
            mid = (silence["start"] + silence["end"]) / 2
            candidates.append({
                "time": mid,
                "priority": 2,
                "type": "silence",
            })
    except Exception as e:
        print(f"[Splitter] Silence detection failed: {e}")

    # Sort candidates by time
    candidates.sort(key=lambda x: x["time"])

    # Select best cut points near target positions
    cut_points = []
    for i in range(1, num_parts):
        target_time = i * target_duration

        # Find best candidate near target_time
        best = _find_nearest_candidate(
            candidates, target_time, max_deviation, min_duration, cut_points
        )

        if best is not None:
            cut_points.append(best)
        else:
            # Fallback: cut at exact target time
            cut_points.append(target_time)

    # Validate: ensure no part is too short
    cut_points = _validate_cut_points(cut_points, total_duration, min_duration)

    return sorted(cut_points)


def _find_nearest_candidate(
    candidates: list[dict],
    target_time: float,
    max_deviation: float,
    min_duration: float,
    existing_cuts: list[float],
) -> Optional[float]:
    """Find the best candidate cut point near target_time."""
    best_candidate = None
    best_score = float("inf")

    for c in candidates:
        time = c["time"]
        distance = abs(time - target_time)

        # Must be within max_deviation
        if distance > max_deviation:
            continue

        # Must not be too close to existing cuts
        too_close = False
        for existing in existing_cuts:
            if abs(time - existing) < min_duration:
                too_close = True
                break
        if too_close:
            continue

        # Score: lower is better (prefer sentence > silence, closer to target)
        priority_weight = c["priority"] * 2  # sentence=2, silence=4
        score = distance + priority_weight

        if score < best_score:
            best_score = score
            best_candidate = time

    return best_candidate


def _validate_cut_points(cut_points: list[float], total_duration: float, min_duration: float) -> list[float]:
    """Remove cut points that would create too-short segments."""
    if not cut_points:
        return []

    valid = []
    prev = 0.0

    for cp in sorted(cut_points):
        if cp - prev >= min_duration and total_duration - cp >= min_duration:
            valid.append(cp)
            prev = cp

    return valid


def _cut_with_fade(video_path: str, output_path: str, start: float, end: float, fade_duration: float):
    """Cut video with fade in/out effects."""
    from modules.ffmpeg_utils import run_ffmpeg

    duration = end - start
    fade_out_start = duration - fade_duration

    run_ffmpeg([
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
        "-vf", f"fade=t=in:st=0:d={fade_duration},fade=t=out:st={fade_out_start}:d={fade_duration}",
        "-af", f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={fade_out_start}:d={fade_duration}",
        "-c:v", "libx264",
        "-crf", "23",
        "-c:a", "aac",
        "-y",
        output_path,
    ])


def _format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python splitter.py <video_path> [--duration 60] [--transcript transcript.json] [--fade 0.5]")
        sys.exit(1)

    video = sys.argv[1]
    duration = 60.0
    transcript_file = None
    fade = 0.0

    for i, arg in enumerate(sys.argv):
        if arg == "--duration" and i + 1 < len(sys.argv):
            duration = float(sys.argv[i + 1])
        elif arg == "--transcript" and i + 1 < len(sys.argv):
            transcript_file = sys.argv[i + 1]
        elif arg == "--fade" and i + 1 < len(sys.argv):
            fade = float(sys.argv[i + 1])

    # Load transcript if provided
    transcript = None
    if transcript_file and os.path.isfile(transcript_file):
        with open(transcript_file, "r", encoding="utf-8") as f:
            transcript = json.load(f)

    # Split
    output_dir = f"{Path(video).stem}_parts"
    parts = smart_split(
        video_path=video,
        output_dir=output_dir,
        target_duration=duration,
        transcript_data=transcript,
        fade_duration=fade,
    )

    print(f"\nTotal: {len(parts)} parts")
    for p in parts:
        print(f"  {p['index']:3d}: {p['path']} ({p['duration']:.1f}s)")
