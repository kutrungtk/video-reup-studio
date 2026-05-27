"""
AI Visual Generator — generate images for video segments via 9router.
Uses text-to-image models available through 9router API.
Falls back to solid color + text overlay if image gen not available.
"""
import subprocess
import os
import json
import urllib.request
from pathlib import Path

WORKSPACE = r"E:\Aiagent\Projects\video-reup-studio\workspace"
FFMPEG = r"E:\Aiagent\Projects\video-reup-studio\ffmpeg_bin\ffmpeg.exe"


def generate_segment_visuals(srt_path: str, api_url: str = "http://localhost:20128/v1",
                              api_key: str = "", model: str = "google/gemini-2.0-flash-001",
                              image_model: str = "", resolution: str = "1080x1920") -> list:
    """
    For each segment in SRT, generate a visual (image or video clip).
    Returns list of {segment_index, image_path, video_path, duration, effect}.
    
    Pipeline:
    1. Parse SRT segments
    2. For each segment: ask LLM for image prompt
    3. Generate image (via image API or fallback to text overlay)
    4. Apply Ken Burns effect → video clip
    """
    from video_effects import parse_srt, ken_burns_effect
    
    segments = parse_srt(srt_path)
    if not segments:
        print("No segments found in SRT")
        return []
    
    # Use project folder (same dir as SRT file) instead of workspace root
    project_dir = os.path.dirname(srt_path)
    visuals_dir = os.path.join(project_dir, "visuals")
    os.makedirs(visuals_dir, exist_ok=True)
    
    results = []
    effects = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]
    
    for i, seg in enumerate(segments):
        print(f"\n[Segment {i+1}/{len(segments)}] {seg['text'][:50]}...")
        
        duration = seg["end"] - seg["start"]
        effect = effects[i % len(effects)]  # rotate effects
        
        # Step 1: Generate image prompt via LLM
        context = " ".join([s["text"] for s in segments])[:200]
        image_prompt = get_image_prompt(seg["text"], context, api_url, api_key, model)
        print(f"  Prompt: {image_prompt[:80]}...")
        
        # Step 2: Generate image
        image_path = os.path.join(visuals_dir, f"segment_{i+1:03d}.png")
        
        if image_model:
            # Try AI image generation
            success = generate_image_api(image_prompt, image_path, api_url, api_key, image_model, resolution)
        else:
            success = False
        
        if not success:
            # Fallback: create styled text overlay image
            success = create_text_visual(seg["text"], image_path, resolution)
        
        if not success:
            print(f"  [WARN] Failed to create visual for segment {i+1}")
            continue
        
        # Step 3: Apply Ken Burns → video clip
        video_path = os.path.join(visuals_dir, f"segment_{i+1:03d}.mp4")
        kb_ok = ken_burns_effect(image_path, video_path, duration=duration, effect=effect, resolution=resolution)
        
        if kb_ok:
            results.append({
                "index": i + 1,
                "image_path": image_path,
                "video_path": video_path,
                "duration": duration,
                "effect": effect,
                "text": seg["text"],
            })
            print(f"  ✓ Video: {video_path} ({duration:.1f}s, {effect})")
        else:
            print(f"  ✕ Ken Burns failed for segment {i+1}")
    
    return results


def get_image_prompt(segment_text: str, context: str, api_url: str, api_key: str, model: str) -> str:
    """Ask LLM to generate a creative image prompt for this segment.
    Inspired by OpenShorts: dramatic, cinematic, viral-worthy visuals."""
    prompt = f"""You are a visual director for viral short-form videos (TikTok, Instagram Reels).
Generate a detailed, creative image prompt for an AI image generator (like DALL-E/GPT Image).

RULES:
- The image will be used as a dramatic background/b-roll in a viral video
- Make it visually stunning, cinematic, eye-catching
- Include lighting, mood, camera angle, style details
- Vertical format (9:16 portrait orientation)
- NO text in the image
- Output ONLY the image prompt (1-3 sentences, under 80 words)

VIDEO SEGMENT TEXT: "{segment_text}"
VIDEO CONTEXT: "{context[:150]}"

Creative image prompt:"""

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": 150,
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(f"{api_url.rstrip('/')}/chat/completions",
                                     data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            result = data["choices"][0]["message"]["content"].strip().strip('"')
            if len(result) > 10:
                return result
    except Exception as e:
        pass
    
    # Fallback: create a decent prompt from segment text
    safe_text = segment_text[:60].encode('ascii', 'ignore').decode()
    return f"Cinematic dramatic scene, dark moody lighting, vertical 9:16 portrait, ultra HD 4k, {safe_text}"


def generate_image_api(prompt: str, output_path: str, api_url: str, api_key: str, 
                       image_model: str, resolution: str = "1080x1920") -> bool:
    """
    Generate image via 9router image API (OpenAI-compatible).
    Model: cx/gpt-5.5-image (or similar)
    Returns base64 PNG or URL.
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    body = json.dumps({
        "model": image_model,
        "prompt": prompt,
        "n": 1,
        "size": "auto",
        "quality": "auto",
        "background": "auto",
        "image_detail": "high",
        "output_format": "png",
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(f"{api_url.rstrip('/')}/images/generations",
                                     data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            
            if "data" not in data or len(data["data"]) == 0:
                print(f"  No image data in response")
                return False
            
            item = data["data"][0]
            
            # Try URL first
            img_url = item.get("url", "")
            if img_url and img_url.startswith("http"):
                urllib.request.urlretrieve(img_url, output_path)
                return os.path.exists(output_path)
            
            # Try base64
            b64_data = item.get("b64_json", "")
            if b64_data:
                import base64
                img_bytes = base64.b64decode(b64_data)
                with open(output_path, "wb") as f:
                    f.write(img_bytes)
                return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
            
            print(f"  No url or b64_json in response")
            return False
    except Exception as e:
        print(f"  Image API error: {str(e)[:100]}")
    
    return False


def create_text_visual(text: str, output_path: str, resolution: str = "1080x1920") -> bool:
    """
    Fallback: create a visually appealing image with text overlay using FFmpeg.
    Dark gradient background + centered text via textfile (avoids escaping issues).
    """
    w, h = resolution.split("x")
    
    # Write text to temp file to avoid escaping issues
    text_file = output_path + ".txt"
    # Wrap long text
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        if len(" ".join(current_line)) > 30:
            lines.append(" ".join(current_line))
            current_line = []
    if current_line:
        lines.append(" ".join(current_line))
    
    with open(text_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    # Create gradient background + text from file
    font_path = "C:/Windows/Fonts/segoeui.ttf"
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/arial.ttf"
    
    # Escape paths for FFmpeg on Windows: replace \ with / and : with \:
    tf_esc = text_file.replace("\\", "/").replace(":", "\\:")
    fp_esc = font_path.replace("\\", "/").replace(":", "\\:")
    
    # Use textfile instead of text= to avoid escaping
    cmd = [
        FFMPEG if os.path.exists(FFMPEG) else "ffmpeg", "-y",
        "-f", "lavfi", "-i",
        f"color=c=0x1a1a2e:s={resolution}:d=1",
        "-vf",
        f"drawtext=textfile='{tf_esc}':fontsize=44:fontcolor=white:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:fontfile='{fp_esc}':"
        f"shadowcolor=black:shadowx=3:shadowy=3",
        "-frames:v", "1",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    
    # Cleanup temp file
    if os.path.exists(text_file):
        os.remove(text_file)
    
    return result.returncode == 0 and os.path.exists(output_path)


def assemble_final_video(visuals: list, audio_path: str, srt_path: str, 
                         output_path: str, subtitle_style: str = "modern") -> bool:
    """
    Final assembly: concatenate visual segments + overlay audio + burn subtitles.
    
    1. Concat all segment videos
    2. Add voice audio
    3. Burn ASS subtitles
    """
    from video_effects import generate_ass_subtitle, crossfade_videos, compose_final_video
    
    if not visuals:
        print("No visuals to assemble")
        return False
    
    # Use project folder (derive from output_path or srt_path)
    project_dir = os.path.dirname(output_path)
    os.makedirs(project_dir, exist_ok=True)
    visuals_dir = os.path.dirname(visuals[0]["video_path"]) if visuals else os.path.join(project_dir, "visuals")
    
    # Step 1: Concat segment videos
    video_paths = [v["video_path"] for v in visuals if os.path.exists(v["video_path"])]
    concat_path = os.path.join(visuals_dir, "concat_visuals.mp4")
    
    if not crossfade_videos(video_paths, concat_path):
        print("Failed to concatenate visuals")
        return False
    print(f"✓ Concatenated {len(video_paths)} segments")
    
    # Step 2: Generate ASS subtitle
    ass_path = os.path.join(visuals_dir, "subtitle.ass")
    generate_ass_subtitle(srt_path, ass_path, style=subtitle_style)
    print(f"✓ Generated ASS subtitle ({subtitle_style})")
    
    # Step 3: Final compose
    success = compose_final_video(concat_path, audio_path, ass_path, output_path)
    if success:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"✓ Final video: {output_path} ({size_mb:.1f}MB)")
    
    return success


if __name__ == "__main__":
    # Quick test
    import sys
    if len(sys.argv) > 1:
        srt = sys.argv[1]
    else:
        srt = os.path.join(WORKSPACE, "test.srt")
    
    print("Generating segment visuals...")
    visuals = generate_segment_visuals(srt)
    print(f"\nGenerated {len(visuals)} visual segments")


def replace_segments_with_ai_visuals(
    segments: list,
    output_dir: str,
    segment_indices: list[int] = None,
    api_url: str = "http://localhost:20128/v1",
    api_key: str = "",
    image_model: str = "",
    resolution: str = "1080x1920",
) -> list:
    """
    Replace specific segments' video with AI-generated visuals.
    Used when:
    - Video source not available (audio-only)
    - User explicitly wants AI visuals for certain segments
    
    Args:
        segments: List of Segment objects (from video_cutter)
        output_dir: Directory to save generated visuals
        segment_indices: Which segments to replace (None = all without video_path)
        api_url: LLM API endpoint
        api_key: API key
        image_model: Image generation model name
        resolution: Output resolution (WxH)
    
    Returns:
        Updated segments list with video_path filled for AI-generated ones
    """
    from video_effects import ken_burns_effect

    visuals_dir = os.path.join(output_dir, "ai_visuals")
    os.makedirs(visuals_dir, exist_ok=True)

    # Determine which segments need AI visuals
    if segment_indices is None:
        # Replace all segments that don't have a video_path
        target_segments = [s for s in segments if not s.video_path or not os.path.isfile(s.video_path)]
    else:
        target_segments = [s for s in segments if s.index in segment_indices]

    if not target_segments:
        print("[AI Visual] No segments need AI visuals")
        return segments

    print(f"[AI Visual] Generating visuals for {len(target_segments)} segments...")

    # Get full context for better prompts
    full_context = " ".join([s.text for s in segments])[:300]
    effects = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]

    for i, seg in enumerate(target_segments):
        print(f"  [{seg.index}] {seg.text[:40]}...")

        # Generate image prompt
        image_prompt = get_image_prompt(seg.text, full_context, api_url, api_key, 
                                        "google/gemini-2.0-flash-001")

        # Generate image
        image_path = os.path.join(visuals_dir, f"seg_{seg.index:03d}.png")
        success = False

        if image_model:
            success = generate_image_api(image_prompt, image_path, api_url, api_key, image_model, resolution)

        if not success:
            success = create_text_visual(seg.text, image_path, resolution)

        if not success:
            print(f"    [WARN] Failed to create visual for segment {seg.index}")
            continue

        # Apply Ken Burns effect → video clip
        video_path = os.path.join(visuals_dir, f"seg_{seg.index:03d}.mp4")
        effect = effects[i % len(effects)]
        duration = seg.duration

        kb_ok = ken_burns_effect(image_path, video_path, duration=duration, effect=effect, resolution=resolution)

        if kb_ok:
            seg.video_path = video_path
            print(f"    ✓ AI visual: {video_path} ({duration:.1f}s, {effect})")
        else:
            print(f"    ✕ Ken Burns failed for segment {seg.index}")

    generated = sum(1 for s in target_segments if s.video_path and os.path.isfile(s.video_path))
    print(f"[AI Visual] Done: {generated}/{len(target_segments)} segments generated")

    return segments
