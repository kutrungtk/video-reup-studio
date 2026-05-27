"""
Video Reup Studio - Subtitle Module
Generate styled ASS subtitles, cover original subs, burn into video.
"""

import json
import os
from pathlib import Path
from typing import Optional


# ASS subtitle style presets
SUBTITLE_STYLES = {
    "default": {
        "fontname": "Arial",
        "fontsize": 48,
        "primary_color": "&H00FFFFFF",   # White
        "outline_color": "&H00000000",   # Black outline
        "back_color": "&H80000000",      # Semi-transparent black
        "bold": True,
        "outline": 3,
        "shadow": 1,
        "alignment": 2,  # Bottom center
        "margin_v": 30,
    },
    "modern": {
        "fontname": "Montserrat",
        "fontsize": 52,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "bold": True,
        "outline": 4,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 40,
    },
    "tiktok": {
        "fontname": "Arial Black",
        "fontsize": 56,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H00000000",
        "bold": True,
        "outline": 4,
        "shadow": 2,
        "alignment": 2,
        "margin_v": 200,  # Higher up for TikTok (avoid bottom UI)
    },
    "cover_original": {
        "fontname": "Arial",
        "fontsize": 48,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&HFF000000",  # Fully opaque black background
        "bold": True,
        "outline": 3,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 20,
        "border_style": 3,  # Opaque box behind text
    },
}


def generate_ass_subtitle(
    transcript_data: dict,
    output_path: str,
    style_name: str = "cover_original",
    custom_style: Optional[dict] = None,
    video_width: int = 1920,
    video_height: int = 1080,
    cover_original_sub: bool = True,
    word_highlight: bool = False,
    highlight_color: str = "&H0000FFFF",  # Yellow highlight
    max_chars_per_line: int = 40,
) -> str:
    """
    Generate ASS subtitle file from transcript.
    
    Args:
        transcript_data: Translated transcript dict
        output_path: Output .ass file path
        style_name: Preset style name
        custom_style: Override style params
        video_width/height: Video dimensions for positioning
        cover_original_sub: Add opaque background to cover original subtitles
        word_highlight: Enable word-by-word highlight (karaoke style)
        highlight_color: Color for highlighted word
        max_chars_per_line: Max characters before line break
    """
    style = SUBTITLE_STYLES.get(style_name, SUBTITLE_STYLES["default"]).copy()
    if custom_style:
        style.update(custom_style)

    # If covering original sub, force opaque box style
    if cover_original_sub:
        style["border_style"] = 3
        style["back_color"] = "&HFF000000"

    # Build ASS content
    ass_content = _build_ass_header(style, video_width, video_height)

    # Add cover strip (opaque rectangle to hide original subs)
    if cover_original_sub:
        ass_content += _build_cover_strip(transcript_data, video_width, video_height)

    # Add subtitle events
    segments = transcript_data.get("segments", [])
    for seg in segments:
        text = seg["text"]
        start = seg["start"]
        end = seg["end"]

        # Word-by-word highlight
        if word_highlight and seg.get("words"):
            ass_content += _build_word_highlight_event(seg, style, highlight_color)
        else:
            # Standard subtitle
            formatted_text = _wrap_text(text, max_chars_per_line)
            start_ts = _seconds_to_ass_time(start)
            end_ts = _seconds_to_ass_time(end)
            ass_content += f"Dialogue: 0,{start_ts},{end_ts},Main,,0,0,0,,{formatted_text}\n"

    # Write file
    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write(ass_content)

    return output_path


def _build_ass_header(style: dict, width: int, height: int) -> str:
    """Build ASS file header with style definitions."""
    border_style = style.get("border_style", 1)

    header = f"""[Script Info]
Title: Video Reup Studio Subtitle
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{style['fontname']},{style['fontsize']},{style['primary_color']},&H000000FF,{style['outline_color']},{style['back_color']},{-1 if style['bold'] else 0},0,0,0,100,100,0,0,{border_style},{style['outline']},{style['shadow']},{style['alignment']},20,20,{style['margin_v']},1
Style: Cover,Arial,10,&H00000000,&H00000000,&H00000000,&HFF000000,0,0,0,0,100,100,0,0,3,0,0,2,0,0,0,1
Style: Highlight,{style['fontname']},{style['fontsize']},&H0000FFFF,&H000000FF,{style['outline_color']},{style['back_color']},{-1 if style['bold'] else 0},0,0,0,100,100,0,0,{border_style},{style['outline']},{style['shadow']},{style['alignment']},20,20,{style['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header


def _build_cover_strip(transcript_data: dict, width: int, height: int) -> str:
    """
    Build opaque strip to cover original subtitles.
    Covers bottom 15% of video during subtitle segments.
    """
    events = ""
    segments = transcript_data.get("segments", [])

    if not segments:
        return events

    # Create continuous cover for entire video duration
    # (original subs might appear at any time)
    duration = transcript_data.get("duration", 0)
    if duration <= 0 and segments:
        duration = segments[-1]["end"] + 1

    # Cover strip: full-width opaque box at bottom
    # Using a drawing command to create a rectangle
    strip_height = int(height * 0.15)  # 15% of video height
    y_pos = height - strip_height

    start_ts = _seconds_to_ass_time(0)
    end_ts = _seconds_to_ass_time(duration)

    # ASS drawing: rectangle covering bottom area
    # {\p1} enables drawing mode, m=move, l=line
    draw_cmd = (
        f"{{\\pos({width // 2},{height - strip_height // 2})"
        f"\\p1\\c&H000000&\\alpha&H30&}}"
        f"m {-width // 2} {-strip_height // 2} "
        f"l {width // 2} {-strip_height // 2} "
        f"l {width // 2} {strip_height // 2} "
        f"l {-width // 2} {strip_height // 2}"
    )

    events += f"Dialogue: -1,{start_ts},{end_ts},Cover,,0,0,0,,{draw_cmd}\n"

    return events


def _build_word_highlight_event(segment: dict, style: dict, highlight_color: str) -> str:
    """Build word-by-word highlight (karaoke-style) subtitle event."""
    events = ""
    words = segment.get("words", [])
    if not words:
        # Fallback to normal
        start_ts = _seconds_to_ass_time(segment["start"])
        end_ts = _seconds_to_ass_time(segment["end"])
        events += f"Dialogue: 0,{start_ts},{end_ts},Main,,0,0,0,,{segment['text']}\n"
        return events

    full_text = " ".join(w["word"] for w in words)
    start_ts = _seconds_to_ass_time(segment["start"])
    end_ts = _seconds_to_ass_time(segment["end"])

    # Build karaoke tags
    # Each word gets highlighted when it's being spoken
    tagged_text = ""
    for i, word in enumerate(words):
        # Duration of this word in centiseconds (ASS karaoke unit)
        word_duration_cs = int((word["end"] - word["start"]) * 100)
        tagged_text += f"{{\\kf{word_duration_cs}}}{word['word']} "

    events += f"Dialogue: 0,{start_ts},{end_ts},Main,,0,0,0,,{tagged_text.strip()}\n"
    return events


def _wrap_text(text: str, max_chars: int) -> str:
    """Wrap long text into multiple lines for subtitle display."""
    if len(text) <= max_chars:
        return text

    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        if len(current_line) + len(word) + 1 <= max_chars:
            current_line += (" " if current_line else "") + word
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    # ASS line break is \N
    return "\\N".join(lines)


def _seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp (H:MM:SS.cc)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def list_styles() -> dict:
    """Return available subtitle style presets."""
    return {name: style for name, style in SUBTITLE_STYLES.items()}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python subtitle.py <transcript.json> [--style cover_original] [--highlight]")
        print(f"Available styles: {list(SUBTITLE_STYLES.keys())}")
        sys.exit(1)

    input_file = sys.argv[1]
    style = "cover_original"
    highlight = False

    for i, arg in enumerate(sys.argv):
        if arg == "--style" and i + 1 < len(sys.argv):
            style = sys.argv[i + 1]
        elif arg == "--highlight":
            highlight = True

    # Load transcript
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Generate subtitle
    output = f"{Path(input_file).stem}.ass"
    generate_ass_subtitle(
        data,
        output,
        style_name=style,
        word_highlight=highlight,
    )
    print(f"Generated: {output}")
