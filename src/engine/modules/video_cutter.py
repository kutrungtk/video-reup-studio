"""
Video Reup Studio - Video Cutter Module
Cut source video into segments based on SRT timestamps.
Each segment corresponds to one subtitle entry.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from engine.modules.ffmpeg_utils import run_ffmpeg, get_video_info


@dataclass
class Segment:
    """A single video/audio segment with timing info."""
    index: int
    start: float  # seconds
    end: float    # seconds
    text: str     # subtitle text for this segment
    video_path: Optional[str] = None
    voice_path: Optional[str] = None

    @property
    def duration(self) -> float:
        return self.end - self.start


def parse_srt(srt_path: str) -> list[Segment]:
    """
    Parse SRT file into list of Segments with timestamps.
    
    SRT format:
    1
    00:00:00,000 --> 00:00:04,500
    Text here
    
    Returns list of Segment objects.
    """
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by double newline (segment separator)
    blocks = re.split(r"\n\s*\n", content.strip())
    segments = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        # Line 1: index
        try:
            index = int(lines[0].strip())
        except ValueError:
            continue

        # Line 2: timestamps
        time_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            lines[1].strip()
        )
        if not time_match:
            continue

        g = time_match.groups()
        start = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
        end = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000

        # Lines 3+: text
        text = "\n".join(lines[2:]).strip()

        segments.append(Segment(
            index=index,
            start=start,
            end=end,
            text=text,
        ))

    return segments


def parse_transcript_data(transcript_data: dict) -> list[Segment]:
    """
    Parse transcript dict (from transcriber/translator module) into Segments.
    
    Expected format:
    {
        "segments": [
            {"start": 0.0, "end": 4.5, "text": "Hello world"},
            ...
        ]
    }
    """
    segments = []
    for i, seg in enumerate(transcript_data.get("segments", []), 1):
        segments.append(Segment(
            index=i,
            start=float(seg["start"]),
            end=float(seg["end"]),
            text=seg.get("text", "").strip(),
        ))
    return segments


def cut_video_by_segments(
    video_path: str,
    segments: list[Segment],
    output_dir: str,
    crop_percent: float = 0.03,
    re_encode: bool = True,
) -> list[Segment]:
    """
    Cut source video into segments based on timestamps.
    Each segment gets a slight crop (anti-reup per segment).
    
    Args:
        video_path: Path to source video
        segments: List of Segment objects with start/end times
        output_dir: Directory to save cut segments
        crop_percent: Random crop per segment (2-5%) for anti-reup
        re_encode: If True, re-encode each segment (slower but exact cuts)
    
    Returns:
        Updated list of Segments with video_path filled in
    """
    os.makedirs(output_dir, exist_ok=True)

    # Get source video info for resolution
    info = get_video_info(video_path)
    print(f"[Cutter] Source: {info.resolution}, {info.duration_str}, {info.fps}fps")
    print(f"[Cutter] Cutting into {len(segments)} segments...")

    for seg in segments:
        output_name = f"seg_{seg.index:03d}.mp4"
        output_path = os.path.join(output_dir, output_name)

        if re_encode:
            # Re-encode for frame-accurate cuts + per-segment crop
            import random
            cp = random.uniform(0.02, crop_percent) if crop_percent > 0 else 0

            vfilters = []
            if cp > 0:
                # Crop slightly different per segment (anti-reup)
                vfilters.append(
                    f"crop=iw*(1-{cp:.4f}):ih*(1-{cp:.4f}):iw*{cp/2:.4f}:ih*{cp/2:.4f}"
                )
                # Scale back to original resolution
                vfilters.append(f"scale={info.width}:{info.height}:flags=lanczos")

            args = [
                "-ss", f"{seg.start:.3f}",
                "-i", video_path,
                "-t", f"{seg.duration:.3f}",
            ]

            if vfilters:
                args += ["-vf", ",".join(vfilters)]

            args += [
                "-c:v", "libx264",
                "-crf", "20",
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "128k",
                "-avoid_negative_ts", "make_zero",
                "-y",
                output_path,
            ]
            run_ffmpeg(args)
        else:
            # Stream copy (fast but may have keyframe issues)
            args = [
                "-ss", f"{seg.start:.3f}",
                "-i", video_path,
                "-t", f"{seg.duration:.3f}",
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-y",
                output_path,
            ]
            run_ffmpeg(args)

        seg.video_path = output_path
        print(f"  [{seg.index:03d}] {seg.start:.1f}s - {seg.end:.1f}s ({seg.duration:.1f}s) → {output_name}")

    print(f"[Cutter] Done. {len(segments)} segments saved to {output_dir}")
    return segments


def cut_from_srt(
    video_path: str,
    srt_path: str,
    output_dir: str,
    crop_percent: float = 0.03,
    re_encode: bool = True,
) -> list[Segment]:
    """
    Convenience function: parse SRT + cut video in one call.
    
    Args:
        video_path: Source video
        srt_path: SRT file with timestamps
        output_dir: Where to save segments
        crop_percent: Per-segment crop for anti-reup
        re_encode: Frame-accurate cuts (True) or fast stream copy (False)
    
    Returns:
        List of Segments with video_path filled
    """
    segments = parse_srt(srt_path)
    if not segments:
        raise ValueError(f"No segments found in SRT: {srt_path}")
    return cut_video_by_segments(video_path, segments, output_dir, crop_percent, re_encode)


def cut_from_transcript(
    video_path: str,
    transcript_data: dict,
    output_dir: str,
    crop_percent: float = 0.03,
    re_encode: bool = True,
) -> list[Segment]:
    """
    Convenience function: parse transcript dict + cut video.
    
    Args:
        video_path: Source video
        transcript_data: Dict with "segments" key
        output_dir: Where to save segments
        crop_percent: Per-segment crop for anti-reup
        re_encode: Frame-accurate cuts
    
    Returns:
        List of Segments with video_path filled
    """
    segments = parse_transcript_data(transcript_data)
    if not segments:
        raise ValueError("No segments found in transcript data")
    return cut_video_by_segments(video_path, segments, output_dir, crop_percent, re_encode)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python video_cutter.py <video_path> <srt_path> [output_dir]")
        sys.exit(1)

    video = sys.argv[1]
    srt = sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) > 3 else "video_segments"

    segments = cut_from_srt(video, srt, out_dir)
    print(f"\nTotal: {len(segments)} segments")
    total_dur = sum(s.duration for s in segments)
    print(f"Total duration: {total_dur:.1f}s")
