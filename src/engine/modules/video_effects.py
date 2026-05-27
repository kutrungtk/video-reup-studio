"""
Video Effects Module — Phase 2
Ken Burns effect, transitions, subtitle styling, AI visual generation.
Uses FFmpeg for all video processing.
"""
import subprocess
import os
import json
import math
import urllib.request
from pathlib import Path


def ken_burns_effect(image_path: str, output_path: str, duration: float = 5.0,
                     effect: str = "zoom_in", fps: int = 30, resolution: str = "1080x1920") -> bool:
    """
    Apply Ken Burns effect to a static image → output video with motion.
    
    Effects:
    - zoom_in: slowly zoom into center
    - zoom_out: start zoomed, slowly zoom out
    - pan_left: pan from right to left
    - pan_right: pan from left to right
    - pan_up: pan from bottom to top
    - pan_down: pan from top to bottom
    - zoom_pan_random: random zoom + pan direction
    """
    w, h = resolution.split("x")
    frames = int(duration * fps)
    
    # zoompan filter parameters based on effect type
    if effect == "zoom_in":
        zp = f"zoompan=z='min(zoom+0.0015,1.5)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={resolution}:fps={fps}"
    elif effect == "zoom_out":
        zp = f"zoompan=z='if(eq(on,1),1.5,max(zoom-0.0015,1.0))':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={resolution}:fps={fps}"
    elif effect == "pan_left":
        zp = f"zoompan=z='1.1':d={frames}:x='iw*0.1+iw*0.8*on/{frames}-iw/zoom/2':y='ih/2-(ih/zoom/2)':s={resolution}:fps={fps}"
    elif effect == "pan_right":
        zp = f"zoompan=z='1.1':d={frames}:x='iw*0.9-iw*0.8*on/{frames}-iw/zoom/2':y='ih/2-(ih/zoom/2)':s={resolution}:fps={fps}"
    elif effect == "pan_up":
        zp = f"zoompan=z='1.1':d={frames}:x='iw/2-(iw/zoom/2)':y='ih*0.8-ih*0.6*on/{frames}':s={resolution}:fps={fps}"
    elif effect == "pan_down":
        zp = f"zoompan=z='1.1':d={frames}:x='iw/2-(iw/zoom/2)':y='ih*0.2+ih*0.6*on/{frames}':s={resolution}:fps={fps}"
    else:  # zoom_pan_random
        import random
        zoom_start = random.uniform(1.0, 1.2)
        zoom_end = random.uniform(1.2, 1.5)
        zp = f"zoompan=z='min({zoom_start}+({zoom_end}-{zoom_start})*on/{frames},{zoom_end})':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={resolution}:fps={fps}"
    
    cmd = [
        get_ffmpeg(), "-y",
        "-loop", "1", "-i", image_path,
        "-vf", zp,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(output_path)


def generate_ass_subtitle(srt_path: str, output_path: str, style: str = "modern") -> bool:
    """
    Convert SRT to ASS with beautiful styling.
    
    Styles:
    - modern: white text, black outline, fade in/out, bottom position
    - karaoke: word-by-word highlight (yellow active, white inactive)
    - bold_shadow: large bold text with heavy shadow
    - minimal: small clean text, slight transparency
    """
    # Parse SRT
    segments = parse_srt(srt_path)
    if not segments:
        return False
    
    # ASS header based on style
    styles = {
        "modern": {
            "fontname": "Segoe UI Semibold",
            "fontsize": 42,
            "primary": "&H00FFFFFF",  # white
            "outline_color": "&H00000000",  # black
            "outline": 3,
            "shadow": 1,
            "alignment": 2,  # bottom center
            "margin_v": 60,
        },
        "karaoke": {
            "fontname": "Segoe UI Bold",
            "fontsize": 38,
            "primary": "&H00FFFFFF",
            "outline_color": "&H00000000",
            "outline": 2,
            "shadow": 0,
            "alignment": 2,
            "margin_v": 50,
        },
        "bold_shadow": {
            "fontname": "Impact",
            "fontsize": 52,
            "primary": "&H00FFFFFF",
            "outline_color": "&H00000000",
            "outline": 4,
            "shadow": 3,
            "alignment": 2,
            "margin_v": 70,
        },
        "minimal": {
            "fontname": "Segoe UI",
            "fontsize": 32,
            "primary": "&H80FFFFFF",  # semi-transparent white
            "outline_color": "&H40000000",
            "outline": 1,
            "shadow": 0,
            "alignment": 2,
            "margin_v": 40,
        },
    }
    
    s = styles.get(style, styles["modern"])
    
    ass_content = f"""[Script Info]
Title: Video Reup Studio Subtitle
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{s['fontname']},{s['fontsize']},{s['primary']},&H000000FF,{s['outline_color']},&H80000000,-1,0,0,0,100,100,0,0,1,{s['outline']},{s['shadow']},{s['alignment']},20,20,{s['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    
    for seg in segments:
        start = format_ass_time(seg["start"])
        end = format_ass_time(seg["end"])
        text = seg["text"].replace("\n", "\\N")
        
        # Add fade effect (200ms in, 200ms out)
        fade = "{\\fad(200,200)}"
        ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{fade}{text}\n"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    
    return True


def crossfade_videos(video_paths: list, output_path: str, fade_duration: float = 0.5) -> bool:
    """
    Concatenate multiple videos with crossfade transitions.
    """
    if len(video_paths) == 0:
        return False
    if len(video_paths) == 1:
        import shutil
        shutil.copy2(video_paths[0], output_path)
        return True
    
    # Build FFmpeg xfade filter chain
    inputs = []
    for v in video_paths:
        inputs.extend(["-i", v])
    
    # Simple concat with crossfade
    filter_parts = []
    n = len(video_paths)
    
    if n == 2:
        # Get duration of first video
        dur = get_duration(video_paths[0])
        offset = max(0, dur - fade_duration)
        filter_parts.append(f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset}[v]")
        cmd = [get_ffmpeg(), "-y"] + inputs + [
            "-filter_complex", filter_parts[0],
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            output_path
        ]
    else:
        # For 3+ videos, use concat demuxer (simpler, no xfade)
        list_file = output_path + ".txt"
        with open(list_file, "w") as f:
            for v in video_paths:
                f.write(f"file '{v}'\n")
        cmd = [get_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", list_file,
               "-c:v", "libx264", "-preset", "fast", "-crf", "23", output_path]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def compose_final_video(video_path: str, audio_path: str, subtitle_path: str,
                        output_path: str, resolution: str = "1080x1920") -> bool:
    """
    Final composition: video + audio + subtitle burn-in.
    """
    w, h = resolution.split("x")
    
    cmd = [get_ffmpeg(), "-y"]
    cmd.extend(["-i", video_path])
    cmd.extend(["-i", audio_path])
    
    # Video filter: scale + subtitle burn-in
    vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
    
    if subtitle_path and os.path.exists(subtitle_path):
        # Escape path for FFmpeg on Windows
        sub_esc = subtitle_path.replace("\\", "/").replace(":", "\\:")
        if subtitle_path.endswith(".ass"):
            vf += f",ass='{sub_esc}'"
        else:
            vf += f",subtitles='{sub_esc}'"
    
    cmd.extend(["-vf", vf])
    cmd.extend(["-map", "0:v", "-map", "1:a", "-shortest"])
    cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23"])
    cmd.extend(["-c:a", "aac", "-b:a", "128k"])
    cmd.extend([output_path])
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode == 0 and os.path.exists(output_path)


def generate_ai_visual_prompt(segment_text: str, context: str, api_url: str, api_key: str = "", model: str = "google/gemini-2.0-flash-001") -> str:
    """
    Use LLM to generate an image prompt for a video segment.
    Returns a detailed image generation prompt.
    """
    prompt = f"""You are a visual director for viral short-form videos.
Given this video segment text, generate a detailed image prompt for an AI image generator.
The image should be dramatic, eye-catching, and suitable as a background/b-roll for this segment.
Output ONLY the image prompt, nothing else. Keep it under 100 words.

Segment text: "{segment_text}"
Video context: "{context}"

Image prompt:"""

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 200,
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(f"{api_url.rstrip('/')}/chat/completions",
                                     data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"dramatic cinematic scene, {segment_text[:50]}, dark moody lighting, 4k"


# ─── Utility functions ───────────────────────────────────────────────────────

def parse_srt(srt_path: str) -> list:
    """Parse SRT file into list of {index, start, end, text}"""
    segments = []
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    blocks = content.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0])
        except ValueError:
            continue
        
        time_line = lines[1]
        if "-->" not in time_line:
            continue
        
        start_str, end_str = time_line.split("-->")
        start = parse_srt_time(start_str.strip())
        end = parse_srt_time(end_str.strip())
        text = "\n".join(lines[2:])
        
        segments.append({"index": idx, "start": start, "end": end, "text": text})
    
    return segments


def parse_srt_time(time_str: str) -> float:
    """Parse SRT timestamp (HH:MM:SS,mmm) to seconds"""
    time_str = time_str.replace(",", ".")
    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def format_ass_time(seconds: float) -> str:
    """Format seconds to ASS timestamp (H:MM:SS.cc)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def get_duration(video_path: str) -> float:
    """Get video duration using ffprobe"""
    ffprobe = get_ffmpeg().replace("ffmpeg", "ffprobe")
    cmd = [ffprobe, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except:
        return 10.0


def get_ffmpeg() -> str:
    """Find FFmpeg binary"""
    project_ffmpeg = r"E:\Aiagent\Projects\video-reup-studio\ffmpeg_bin\ffmpeg.exe"
    if os.path.exists(project_ffmpeg):
        return project_ffmpeg
    return "ffmpeg"
