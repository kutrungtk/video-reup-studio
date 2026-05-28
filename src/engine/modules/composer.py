"""
Video Reup Studio - Composer Module
Compose final video from cut segments + voice segments.
Handles duration mismatch between video and voice per segment.
"""

import os
import json
from dataclasses import dataclass
from typing import Optional

from engine.modules.ffmpeg_utils import run_ffmpeg, get_video_info, concat_videos
from engine.modules.video_cutter import Segment


@dataclass
class ComposeConfig:
    """Configuration for composition."""
    # Duration mismatch strategy
    # "slow_video": slow down video to match voice duration
    # "freeze_last": freeze last frame of video if voice is longer
    # "trim_voice": trim voice to match video duration
    # "pad_silence": pad silence at end of voice if shorter
    mismatch_strategy: str = "freeze_last"

    # Tolerance: if difference < this, don't adjust (seconds)
    tolerance: float = 0.3

    # Subtitle
    burn_subtitle: bool = True
    subtitle_style: str = "default"

    # Transitions
    transition_type: str = "none"       # none, crossfade, fade_black, fade_white
    transition_duration: float = 0.5    # seconds
    fade_in: float = 0.0               # fade in at start of final video
    fade_out: float = 0.0              # fade out at end of final video

    # Output
    output_codec: str = "libx264"
    output_crf: int = 20
    output_preset: str = "medium"


def get_audio_duration(audio_path: str) -> float:
    """Get duration of audio file in seconds."""
    from engine.modules.ffmpeg_utils import run_ffprobe
    data = run_ffprobe(["-show_format", audio_path])
    return float(data.get("format", {}).get("duration", 0))


def compose_segment(
    segment: Segment,
    output_path: str,
    config: ComposeConfig = None,
) -> str:
    """
    Compose a single segment: video + voice with duration sync.
    
    Logic:
    - If voice duration ≈ video duration (within tolerance): just replace audio
    - If voice > video: freeze last frame OR slow down video
    - If voice < video: pad silence OR trim video
    
    Args:
        segment: Segment with video_path and voice_path set
        output_path: Where to save composed segment
        config: ComposeConfig options
    
    Returns:
        Path to composed segment
    """
    if config is None:
        config = ComposeConfig()

    if not segment.video_path or not os.path.isfile(segment.video_path):
        raise FileNotFoundError(f"Video segment not found: {segment.video_path}")

    # If no voice, just copy video segment
    if not segment.voice_path or not os.path.isfile(segment.voice_path):
        import shutil
        shutil.copy2(segment.video_path, output_path)
        return output_path

    video_dur = segment.duration
    voice_dur = get_audio_duration(segment.voice_path)
    diff = voice_dur - video_dur

    print(f"  [{segment.index:03d}] video={video_dur:.2f}s, voice={voice_dur:.2f}s, diff={diff:+.2f}s", end="")

    if abs(diff) <= config.tolerance:
        # Within tolerance — just replace audio, trim to shorter
        print(" → direct replace")
        _compose_direct(segment.video_path, segment.voice_path, output_path, config)

    elif diff > 0:
        # Voice is LONGER than video
        if config.mismatch_strategy == "slow_video":
            print(" → slow video")
            _compose_slow_video(segment.video_path, segment.voice_path, output_path, video_dur, voice_dur, config)
        elif config.mismatch_strategy == "freeze_last":
            print(" → freeze last frame")
            _compose_freeze_last(segment.video_path, segment.voice_path, output_path, video_dur, voice_dur, config)
        else:
            # trim_voice fallback
            print(" → trim voice")
            _compose_trim_voice(segment.video_path, segment.voice_path, output_path, video_dur, config)

    else:
        # Voice is SHORTER than video — pad silence or trim video
        if config.mismatch_strategy == "trim_voice":
            # Actually trim video to voice length
            print(" → trim video")
            _compose_trim_video(segment.video_path, segment.voice_path, output_path, voice_dur, config)
        else:
            # Pad silence at end of voice
            print(" → pad silence")
            _compose_pad_silence(segment.video_path, segment.voice_path, output_path, video_dur, voice_dur, config)

    return output_path


def _compose_direct(video_path: str, voice_path: str, output_path: str, config: ComposeConfig):
    """Replace video audio with voice, trim to shorter duration."""
    run_ffmpeg([
        "-i", video_path,
        "-i", voice_path,
        "-c:v", config.output_codec,
        "-crf", str(config.output_crf),
        "-preset", config.output_preset,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-y",
        output_path,
    ])


def _compose_slow_video(video_path: str, voice_path: str, output_path: str,
                         video_dur: float, voice_dur: float, config: ComposeConfig):
    """Slow down video to match voice duration."""
    speed_factor = video_dur / voice_dur  # < 1.0 means slower
    pts_factor = 1.0 / speed_factor  # > 1.0 means slower playback

    run_ffmpeg([
        "-i", video_path,
        "-i", voice_path,
        "-filter_complex",
        f"[0:v]setpts={pts_factor:.6f}*PTS[vout]",
        "-map", "[vout]",
        "-map", "1:a:0",
        "-c:v", config.output_codec,
        "-crf", str(config.output_crf),
        "-preset", config.output_preset,
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-y",
        output_path,
    ])


def _compose_freeze_last(video_path: str, voice_path: str, output_path: str,
                          video_dur: float, voice_dur: float, config: ComposeConfig):
    """Freeze last frame of video to extend it to voice duration."""
    extra_time = voice_dur - video_dur

    # Use tpad filter to freeze last frame
    run_ffmpeg([
        "-i", video_path,
        "-i", voice_path,
        "-filter_complex",
        f"[0:v]tpad=stop_mode=clone:stop_duration={extra_time:.3f}[vout]",
        "-map", "[vout]",
        "-map", "1:a:0",
        "-c:v", config.output_codec,
        "-crf", str(config.output_crf),
        "-preset", config.output_preset,
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-y",
        output_path,
    ])


def _compose_trim_voice(video_path: str, voice_path: str, output_path: str,
                         video_dur: float, config: ComposeConfig):
    """Trim voice to match video duration."""
    run_ffmpeg([
        "-i", video_path,
        "-i", voice_path,
        "-c:v", config.output_codec,
        "-crf", str(config.output_crf),
        "-preset", config.output_preset,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:a", "aac",
        "-b:a", "128k",
        "-t", f"{video_dur:.3f}",
        "-y",
        output_path,
    ])


def _compose_trim_video(video_path: str, voice_path: str, output_path: str,
                         voice_dur: float, config: ComposeConfig):
    """Trim video to match voice duration (voice is shorter)."""
    run_ffmpeg([
        "-i", video_path,
        "-i", voice_path,
        "-c:v", config.output_codec,
        "-crf", str(config.output_crf),
        "-preset", config.output_preset,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:a", "aac",
        "-b:a", "128k",
        "-t", f"{voice_dur:.3f}",
        "-y",
        output_path,
    ])


def _compose_pad_silence(video_path: str, voice_path: str, output_path: str,
                          video_dur: float, voice_dur: float, config: ComposeConfig):
    """Pad silence at end of voice to match video duration."""
    pad_duration = video_dur - voice_dur

    run_ffmpeg([
        "-i", video_path,
        "-i", voice_path,
        "-filter_complex",
        f"[1:a]apad=pad_dur={pad_duration:.3f}[aout]",
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", config.output_codec,
        "-crf", str(config.output_crf),
        "-preset", config.output_preset,
        "-c:a", "aac",
        "-b:a", "128k",
        "-t", f"{video_dur:.3f}",
        "-y",
        output_path,
    ])


def compose_all_segments(
    segments: list[Segment],
    output_dir: str,
    final_output: str,
    config: ComposeConfig = None,
    subtitle_path: Optional[str] = None,
) -> str:
    """
    Compose all segments and concatenate into final video.
    
    Args:
        segments: List of Segments with video_path and voice_path set
        output_dir: Working directory for intermediate files
        final_output: Path for final concatenated video
        config: ComposeConfig options
        subtitle_path: Optional SRT/ASS to burn after concat
    
    Returns:
        Path to final composed video
    """
    if config is None:
        config = ComposeConfig()

    composed_dir = os.path.join(output_dir, "composed")
    os.makedirs(composed_dir, exist_ok=True)

    print(f"[Composer] Composing {len(segments)} segments...")

    composed_paths = []
    for seg in segments:
        out_path = os.path.join(composed_dir, f"composed_{seg.index:03d}.mp4")
        compose_segment(seg, out_path, config)
        composed_paths.append(out_path)

    # Concatenate all composed segments (with transitions if configured)
    print(f"[Composer] Concatenating {len(composed_paths)} segments...")

    concat_output = final_output if not subtitle_path else os.path.join(output_dir, "concat_no_sub.mp4")

    if config.transition_type != "none" and len(composed_paths) > 1:
        # Use transitions module
        from engine.modules.transitions import concat_with_transitions, TransitionConfig
        trans_config = TransitionConfig(
            transition_type=config.transition_type,
            duration=config.transition_duration,
            fade_in=config.fade_in,
            fade_out=config.fade_out,
        )
        concat_with_transitions(composed_paths, concat_output, trans_config)
    else:
        _concat_with_reencode(composed_paths, concat_output, config)

    # Burn subtitle if provided
    if subtitle_path and os.path.isfile(subtitle_path):
        print(f"[Composer] Burning subtitle: {subtitle_path}")
        from engine.modules.ffmpeg_utils import burn_subtitle
        burn_subtitle(concat_output, subtitle_path, final_output)
        # Clean intermediate
        if concat_output != final_output:
            os.remove(concat_output)
    else:
        if concat_output != final_output:
            os.rename(concat_output, final_output)

    print(f"[Composer] Done: {final_output}")
    return final_output


def _concat_with_reencode(video_paths: list[str], output_path: str, config: ComposeConfig):
    """
    Concatenate videos with re-encode to ensure compatibility.
    Uses filter_complex concat for segments that may differ in duration.
    """
    if len(video_paths) == 1:
        import shutil
        shutil.copy2(video_paths[0], output_path)
        return

    # Use concat demuxer (faster, works when all segments have same codec params)
    concat_file = output_path + ".txt"
    with open(concat_file, "w", encoding="utf-8") as f:
        for vp in video_paths:
            # Escape single quotes in path
            escaped = vp.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    run_ffmpeg([
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c:v", config.output_codec,
        "-crf", str(config.output_crf),
        "-preset", config.output_preset,
        "-c:a", "aac",
        "-b:a", "128k",
        "-y",
        output_path,
    ])

    # Cleanup
    os.remove(concat_file)


if __name__ == "__main__":
    import sys

    print("Composer module - use via pipeline or import directly.")
    print("Example:")
    print("  from engine.modules.composer import compose_all_segments")
    print("  from engine.modules.video_cutter import cut_from_srt, Segment")
    print("")
    print("  segments = cut_from_srt('video.mp4', 'sub.srt', 'segments/')")
    print("  # ... assign voice_path to each segment ...")
    print("  compose_all_segments(segments, 'work/', 'final.mp4')")
