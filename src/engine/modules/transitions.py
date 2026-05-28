"""
Video Reup Studio - Transitions Module
Apply crossfade/fade transitions between video segments during composition.
"""

import os
from dataclasses import dataclass
from typing import Optional

from engine.modules.ffmpeg_utils import run_ffmpeg


@dataclass
class TransitionConfig:
    """Configuration for transitions between segments."""
    # Transition type: "crossfade", "fade_black", "fade_white", "none"
    transition_type: str = "crossfade"
    
    # Duration of transition in seconds
    duration: float = 0.5
    
    # Fade in/out for first/last segment
    fade_in: float = 0.3   # Fade in at start of video
    fade_out: float = 0.3  # Fade out at end of video


def apply_crossfade(
    video_a: str,
    video_b: str,
    output_path: str,
    duration: float = 0.5,
) -> str:
    """
    Apply crossfade transition between two video segments.
    The last `duration` seconds of video_a overlap with first `duration` seconds of video_b.
    
    Args:
        video_a: First video segment
        video_b: Second video segment
        output_path: Output path
        duration: Crossfade duration in seconds
    
    Returns:
        Path to output video
    """
    run_ffmpeg([
        "-i", video_a,
        "-i", video_b,
        "-filter_complex",
        f"[0:v][1:v]xfade=transition=fade:duration={duration:.3f}:offset={{offset}}[vout];"
        f"[0:a][1:a]acrossfade=d={duration:.3f}[aout]",
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-crf", "20",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-y",
        output_path,
    ])
    return output_path


def apply_fade_black(
    video_a: str,
    video_b: str,
    output_path: str,
    duration: float = 0.5,
) -> str:
    """
    Fade to black between two segments, then fade in from black.
    """
    # Fade out video_a, then fade in video_b, concat
    temp_a = output_path + ".a.mp4"
    temp_b = output_path + ".b.mp4"

    # Fade out last frames of A
    run_ffmpeg([
        "-i", video_a,
        "-vf", f"fade=t=out:st={{st_a}}:d={duration:.3f}",
        "-af", f"afade=t=out:st={{st_a}}:d={duration:.3f}",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-c:a", "aac", "-y", temp_a,
    ])

    # Fade in first frames of B
    run_ffmpeg([
        "-i", video_b,
        "-vf", f"fade=t=in:st=0:d={duration:.3f}",
        "-af", f"afade=t=in:st=0:d={duration:.3f}",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-c:a", "aac", "-y", temp_b,
    ])

    # Concat
    from engine.modules.ffmpeg_utils import concat_videos
    concat_videos([temp_a, temp_b], output_path)

    # Cleanup
    for f in [temp_a, temp_b]:
        if os.path.exists(f):
            os.remove(f)

    return output_path


def concat_with_transitions(
    video_paths: list[str],
    output_path: str,
    config: TransitionConfig = None,
) -> str:
    """
    Concatenate multiple video segments with transitions between them.
    
    Uses FFmpeg xfade filter for crossfade transitions.
    For many segments, builds a complex filter chain.
    
    Args:
        video_paths: List of video segment paths (in order)
        output_path: Final output path
        config: TransitionConfig options
    
    Returns:
        Path to output video with transitions
    """
    if config is None:
        config = TransitionConfig()

    if not video_paths:
        raise ValueError("No video paths provided")

    if len(video_paths) == 1:
        import shutil
        shutil.copy2(video_paths[0], output_path)
        return output_path

    if config.transition_type == "none":
        # No transitions, just concat
        from engine.modules.ffmpeg_utils import concat_videos
        return concat_videos(video_paths, output_path)

    # For crossfade: use xfade filter chain
    if config.transition_type == "crossfade":
        return _concat_xfade(video_paths, output_path, config.duration, config.fade_in, config.fade_out)
    elif config.transition_type in ("fade_black", "fade_white"):
        return _concat_fade(video_paths, output_path, config)
    else:
        # Fallback to simple concat
        from engine.modules.ffmpeg_utils import concat_videos
        return concat_videos(video_paths, output_path)


def _concat_xfade(
    video_paths: list[str],
    output_path: str,
    xfade_duration: float,
    fade_in: float,
    fade_out: float,
) -> str:
    """
    Concatenate with xfade transitions using complex filter graph.
    Handles N segments by chaining xfade filters.
    """
    from engine.modules.ffmpeg_utils import run_ffprobe

    n = len(video_paths)

    # Get durations of all segments
    durations = []
    for vp in video_paths:
        data = run_ffprobe(["-show_format", vp])
        dur = float(data.get("format", {}).get("duration", 0))
        durations.append(dur)

    # Build input args
    inputs = []
    for vp in video_paths:
        inputs += ["-i", vp]

    # Build xfade filter chain
    # For N videos, we need N-1 xfade operations
    # Each xfade takes two inputs and produces one output
    video_filters = []
    audio_filters = []

    # Calculate offsets (when each transition starts)
    # offset[i] = sum of durations[0..i] - sum of xfade_durations[0..i-1]
    offsets = []
    cumulative = 0.0
    for i in range(n - 1):
        cumulative += durations[i] - xfade_duration
        offsets.append(max(0, cumulative))
        # Reset cumulative to account for shortened duration
        cumulative = offsets[-1]

    # Recalculate offsets properly
    offsets = []
    running_offset = 0.0
    for i in range(n - 1):
        if i == 0:
            running_offset = durations[0] - xfade_duration
        else:
            running_offset += durations[i] - xfade_duration
        offsets.append(max(0, running_offset))

    # Build video xfade chain
    if n == 2:
        # Simple case: just one xfade
        video_filters.append(
            f"[0:v][1:v]xfade=transition=fade:duration={xfade_duration:.3f}:offset={offsets[0]:.3f}[vout]"
        )
        audio_filters.append(
            f"[0:a][1:a]acrossfade=d={xfade_duration:.3f}[aout]"
        )
    else:
        # Chain xfades for N > 2
        # First xfade
        video_filters.append(
            f"[0:v][1:v]xfade=transition=fade:duration={xfade_duration:.3f}:offset={offsets[0]:.3f}[v01]"
        )
        audio_filters.append(
            f"[0:a][1:a]acrossfade=d={xfade_duration:.3f}[a01]"
        )

        # Middle xfades
        for i in range(2, n):
            prev_label = f"v{i-2:02d}{i-1:02d}" if i > 2 else "v01"
            out_label = f"v{i-1:02d}{i:02d}" if i < n - 1 else "vout"
            
            # Recalculate offset relative to the accumulated output
            rel_offset = offsets[i-1] if i-1 < len(offsets) else offsets[-1]
            
            video_filters.append(
                f"[{prev_label}][{i}:v]xfade=transition=fade:duration={xfade_duration:.3f}:offset={rel_offset:.3f}[{out_label}]"
            )

            a_prev = f"a{i-2:02d}{i-1:02d}" if i > 2 else "a01"
            a_out = f"a{i-1:02d}{i:02d}" if i < n - 1 else "aout"
            audio_filters.append(
                f"[{a_prev}][{i}:a]acrossfade=d={xfade_duration:.3f}[{a_out}]"
            )

    # Add fade in/out
    fade_filters = []
    if fade_in > 0:
        fade_filters.append(f"fade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        # Calculate total output duration
        total_dur = sum(durations) - xfade_duration * (n - 1)
        fade_start = max(0, total_dur - fade_out)
        fade_filters.append(f"fade=t=out:st={fade_start:.3f}:d={fade_out:.3f}")

    # If we have fade in/out, chain them after xfade
    if fade_filters:
        # Replace [vout] with intermediate, add fade
        if video_filters:
            last_filter = video_filters[-1]
            video_filters[-1] = last_filter.replace("[vout]", "[vpre]")
            video_filters.append(f"[vpre]{','.join(fade_filters)}[vout]")
        else:
            video_filters.append(f"[0:v]{','.join(fade_filters)}[vout]")

    # Combine filter complex
    all_filters = video_filters + audio_filters
    filter_complex = ";".join(all_filters)

    # Build full command
    args = inputs + [
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-crf", "20",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-y",
        output_path,
    ]

    print(f"[Transitions] Applying crossfade ({xfade_duration}s) between {n} segments...")
    run_ffmpeg(args)
    print(f"[Transitions] Done: {output_path}")

    return output_path


def _concat_fade(
    video_paths: list[str],
    output_path: str,
    config: TransitionConfig,
) -> str:
    """
    Concatenate with fade-to-black (or white) between segments.
    Each segment gets fade out at end + fade in at start.
    """
    from engine.modules.ffmpeg_utils import run_ffprobe

    color = "black" if config.transition_type == "fade_black" else "white"
    dur = config.duration
    temp_dir = output_path + "_temp"
    os.makedirs(temp_dir, exist_ok=True)

    processed = []
    for i, vp in enumerate(video_paths):
        # Get duration
        data = run_ffprobe(["-show_format", vp])
        seg_dur = float(data.get("format", {}).get("duration", 0))

        temp_out = os.path.join(temp_dir, f"fade_{i:03d}.mp4")
        fade_out_start = max(0, seg_dur - dur)

        vf_parts = []
        af_parts = []

        # Fade in (except first segment if fade_in is handled separately)
        if i > 0:
            vf_parts.append(f"fade=t=in:st=0:d={dur:.3f}:color={color}")
            af_parts.append(f"afade=t=in:st=0:d={dur:.3f}")

        # Fade out (except last segment if fade_out is handled separately)
        if i < len(video_paths) - 1:
            vf_parts.append(f"fade=t=out:st={fade_out_start:.3f}:d={dur:.3f}:color={color}")
            af_parts.append(f"afade=t=out:st={fade_out_start:.3f}:d={dur:.3f}")

        args = ["-i", vp]
        if vf_parts:
            args += ["-vf", ",".join(vf_parts)]
        if af_parts:
            args += ["-af", ",".join(af_parts)]
        args += ["-c:v", "libx264", "-crf", "20", "-preset", "fast", "-c:a", "aac", "-y", temp_out]

        run_ffmpeg(args)
        processed.append(temp_out)

    # Concat all processed segments
    from engine.modules.ffmpeg_utils import concat_videos
    concat_videos(processed, output_path)

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

    print(f"[Transitions] Fade-to-{color} applied between {len(video_paths)} segments")
    return output_path


if __name__ == "__main__":
    import sys
    print("Transitions module — use via composer or import directly.")
    print("Example:")
    print("  from engine.modules.transitions import concat_with_transitions, TransitionConfig")
    print("  config = TransitionConfig(transition_type='crossfade', duration=0.5)")
    print("  concat_with_transitions(['seg1.mp4', 'seg2.mp4', 'seg3.mp4'], 'output.mp4', config)")
