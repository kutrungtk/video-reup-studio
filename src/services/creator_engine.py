"""
Video Reup Studio Rebuild — Creator Engine
Orchestrates the Creator workflow: Script → Scenes → Visuals → Voice → Music → Compose
"""

import os
import json
import time
from typing import Optional
from dataclasses import dataclass, field

from services.llm_client import get_llm
from services.visual_effects import image_to_video, image_to_video_batch, build_visual_prompt, EFFECTS
from engine.modules.ffmpeg_utils import run_ffmpeg, concat_videos


@dataclass
class Scene:
    """A single scene in the creator workflow."""
    index: int
    text: str                          # Narration text
    duration: float = 5.0              # Estimated duration (seconds)
    image_path: str = ""               # Generated/selected image
    video_path: str = ""               # Video clip for this scene
    voice_path: str = ""               # Voice narration audio
    effect: str = "random"             # Visual effect
    camera_move: str = ""              # Camera move for AI prompt
    status: str = "pending"            # pending, generating, done, error


@dataclass
class CreatorConfig:
    """Configuration for creator workflow."""
    # Script
    topic: str = ""
    style: str = "news"                # news, storytelling, educational, review, viral
    length: str = "short"              # short (30-60s), medium (1-3min), long (3-5min)
    language: str = "it"

    # Visuals
    visual_mode: str = "ai_image"      # ai_image, local_images, mixed
    effect_mode: str = "varied"        # varied (cycle effects), single, random
    resolution: str = "1080x1920"
    fps: int = 30

    # Voice
    voice_engine: str = "omnivoice"
    voice_ref: str = ""                # Reference audio for clone
    voice_instruct: str = ""           # Style instruction
    voice_speed: float = 1.0

    # Music
    music_path: str = ""
    music_volume: float = 0.2          # 0.0-1.0
    music_fade: bool = True

    # Output
    output_dir: str = ""
    burn_subtitle: bool = True
    anti_reup: bool = True
    transition: str = "crossfade"      # crossfade, fade_black, none


def generate_script(topic: str, style: str, length: str, language: str) -> str:
    """
    Generate video script from topic using LLM.
    
    Returns script text with scenes separated by ---
    """
    length_guide = {
        "short": "4-6 scenes, each 1-2 sentences. Total ~30-60 seconds narration.",
        "medium": "8-12 scenes, each 2-3 sentences. Total ~1-3 minutes narration.",
        "long": "15-20 scenes, each 2-4 sentences. Total ~3-5 minutes narration.",
    }

    style_guide = {
        "news": "Objective, factual, professional news anchor tone. Start with hook.",
        "storytelling": "Engaging narrative, build tension, emotional arc.",
        "educational": "Clear explanations, step-by-step, use analogies.",
        "review": "Balanced opinion, pros/cons, personal experience.",
        "viral": "Strong hook in first 3 seconds, shocking facts, fast pace.",
    }

    prompt = f"""Write a video script about: {topic}

Style: {style_guide.get(style, style)}
Length: {length_guide.get(length, length)}
Language: {language}

FORMAT RULES:
- Separate each scene with ---
- Each scene = 1 narration segment (what the narrator says)
- Keep sentences short and punchy (for TTS)
- First scene MUST be a strong hook
- Last scene = call to action or conclusion
- Do NOT include scene numbers, timestamps, or stage directions
- Output ONLY the narration text

Example format:
Breaking news today: AI is changing everything we know about work.
---
According to a new report, 50 percent of office jobs will be automated by 2027.
---
Experts recommend learning new skills immediately.
"""

    llm = get_llm()
    result = llm.chat(
        messages=[
            {"role": "system", "content": "You are a professional video scriptwriter. Write engaging, concise scripts for short-form video content."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=2048,
    )

    return result.strip()


def split_script_to_scenes(script_text: str) -> list[Scene]:
    """Split script text into Scene objects."""
    if "---" in script_text:
        parts = [p.strip() for p in script_text.split("---") if p.strip()]
    else:
        parts = [p.strip() for p in script_text.split("\n\n") if p.strip()]

    scenes = []
    for i, text in enumerate(parts, 1):
        # Estimate duration: ~2.5 words/second for narration
        words = len(text.split())
        duration = max(3.0, words / 2.5)

        scenes.append(Scene(
            index=i,
            text=text,
            duration=round(duration, 1),
        ))

    return scenes


def generate_visuals_for_scenes(
    scenes: list[Scene],
    output_dir: str,
    config: CreatorConfig,
    progress_cb=None,
    check_cancelled=None,
) -> list[Scene]:
    """
    Generate visual (image → video) for each scene.
    Uses AI image generation + visual effects.
    """
    visuals_dir = os.path.join(output_dir, "visuals")
    os.makedirs(visuals_dir, exist_ok=True)

    effect_list = [k for k in EFFECTS.keys() if k not in ("random", "static")]
    total = len(scenes)

    for i, scene in enumerate(scenes):
        if check_cancelled:
            check_cancelled()

        scene.status = "generating"

        # Generate image for this scene
        if config.visual_mode == "ai_image":
            image_path = os.path.join(visuals_dir, f"scene_{scene.index:03d}.png")
            scene.image_path = _generate_ai_image(scene.text, image_path, config)
        elif scene.image_path and os.path.isfile(scene.image_path):
            pass  # Use existing local image
        else:
            # Fallback: create text-on-color image
            image_path = os.path.join(visuals_dir, f"scene_{scene.index:03d}.png")
            scene.image_path = _create_text_image(scene.text, image_path, config.resolution)

        # Convert image to video with effect
        if scene.image_path and os.path.isfile(scene.image_path):
            video_path = os.path.join(visuals_dir, f"scene_{scene.index:03d}.mp4")

            # Select effect
            if config.effect_mode == "varied":
                effect = effect_list[i % len(effect_list)]
            elif config.effect_mode == "random":
                effect = "random"
            else:
                effect = config.effect_mode if config.effect_mode in EFFECTS else "zoom_in"

            scene.effect = effect
            image_to_video(
                scene.image_path, video_path,
                duration=scene.duration,
                effect=effect,
                resolution=config.resolution,
                fps=config.fps,
            )
            scene.video_path = video_path
            scene.status = "done"
        else:
            scene.status = "error"

        if progress_cb:
            progress_cb(int((i + 1) / total * 100), f"Visual {i+1}/{total}: {scene.effect}")

    return scenes


def generate_voice_for_scenes(
    scenes: list[Scene],
    output_dir: str,
    config: CreatorConfig,
    progress_cb=None,
    check_cancelled=None,
) -> list[Scene]:
    """Generate voice narration for each scene."""
    import sys
    engine_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
    modules_dir = os.path.join(engine_dir, "modules")
    for p in [engine_dir, modules_dir]:
        if p not in sys.path:
            sys.path.insert(0, p)

    from engine.modules.tts_engine import VoiceConfig, _run_omnivoice, _run_edge_tts

    voice_dir = os.path.join(output_dir, "voice")
    os.makedirs(voice_dir, exist_ok=True)

    total = len(scenes)
    for i, scene in enumerate(scenes):
        if check_cancelled:
            check_cancelled()

        if not scene.text.strip():
            continue

        output_path = os.path.join(voice_dir, f"scene_{scene.index:03d}.wav")

        if config.voice_engine == "omnivoice":
            ok = _run_omnivoice(
                text=scene.text,
                output_path=output_path,
                language=config.language,
                speed=config.voice_speed,
                ref_audio=config.voice_ref,
                instruct=config.voice_instruct,
            )
            if not ok:
                # Fallback edge-tts
                output_path = os.path.join(voice_dir, f"scene_{scene.index:03d}.mp3")
                ok = _run_edge_tts(scene.text, output_path, config.language)
        else:
            output_path = os.path.join(voice_dir, f"scene_{scene.index:03d}.mp3")
            ok = _run_edge_tts(scene.text, output_path, config.language)

        if ok and os.path.isfile(output_path):
            scene.voice_path = output_path
            # Update duration based on actual voice length
            from engine.modules.tts_engine import get_audio_duration
            actual_dur = get_audio_duration(output_path)
            if actual_dur > 0:
                scene.duration = actual_dur

        if progress_cb:
            progress_cb(int((i + 1) / total * 100), f"Voice {i+1}/{total}")

    return scenes


def compose_creator_video(
    scenes: list[Scene],
    output_dir: str,
    config: CreatorConfig,
    progress_cb=None,
) -> str:
    """
    Compose final video from all scenes.
    Merges: video clips + voice + subtitle + music → final.mp4
    """
    compose_dir = os.path.join(output_dir, "compose")
    os.makedirs(compose_dir, exist_ok=True)

    # Step 1: Merge voice into each scene video
    merged_clips = []
    for scene in scenes:
        if not scene.video_path or not os.path.isfile(scene.video_path):
            continue

        merged_path = os.path.join(compose_dir, f"merged_{scene.index:03d}.mp4")

        if scene.voice_path and os.path.isfile(scene.voice_path):
            # Merge voice into video (replace audio)
            run_ffmpeg([
                "-i", scene.video_path,
                "-i", scene.voice_path,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest",
                "-y", merged_path,
            ])
        else:
            # No voice, use video as-is (silent)
            import shutil
            shutil.copy2(scene.video_path, merged_path)

        merged_clips.append(merged_path)

    if not merged_clips:
        raise ValueError("No video clips to compose")

    if progress_cb:
        progress_cb(40, "Concatenating scenes...")

    # Step 2: Concat all clips (with transitions if configured)
    concat_path = os.path.join(compose_dir, "concat.mp4")

    if config.transition != "none" and len(merged_clips) > 1:
        from engine.modules.transitions import concat_with_transitions, TransitionConfig
        trans_config = TransitionConfig(
            transition_type=config.transition,
            duration=0.5,
        )
        concat_with_transitions(merged_clips, concat_path, trans_config)
    else:
        concat_videos(merged_clips, concat_path)

    if progress_cb:
        progress_cb(60, "Adding music...")

    # Step 3: Add background music (if provided)
    if config.music_path and os.path.isfile(config.music_path):
        music_output = os.path.join(compose_dir, "with_music.mp4")
        _add_background_music(concat_path, config.music_path, music_output,
                              volume=config.music_volume, fade=config.music_fade)
        current = music_output
    else:
        current = concat_path

    if progress_cb:
        progress_cb(80, "Burning subtitle...")

    # Step 4: Burn subtitle (if enabled)
    final_path = os.path.join(output_dir, "final.mp4")

    if config.burn_subtitle:
        srt_path = _generate_srt_from_scenes(scenes, os.path.join(output_dir, "subtitle.srt"))
        from engine.modules.ffmpeg_utils import burn_subtitle
        burn_subtitle(current, srt_path, final_path)
    else:
        import shutil
        shutil.copy2(current, final_path)

    if progress_cb:
        progress_cb(100, "Done!")

    return final_path


def _generate_ai_image(scene_text: str, output_path: str, config: CreatorConfig) -> str:
    """Generate AI image for a scene via LLM + image API."""
    try:
        from config.settings import get_settings
        settings = get_settings()

        # Generate image prompt
        prompt = build_visual_prompt(scene_text, style="cinematic dramatic")

        # Call image API
        import requests
        endpoint = settings.get("image_endpoint") or settings.get("llm_endpoint")
        api_key = settings.get("api_key")
        model = settings.get("image_model") or "auto"

        url = f"{endpoint.rstrip('/')}/images/generations"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = requests.post(url, json={
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": config.resolution.replace("x", "x"),
        }, headers=headers, timeout=60)

        if resp.status_code == 200:
            data = resp.json()
            # Handle base64 or URL response
            if "data" in data and data["data"]:
                img_data = data["data"][0]
                if "b64_json" in img_data:
                    import base64
                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(img_data["b64_json"]))
                    return output_path
                elif "url" in img_data:
                    img_resp = requests.get(img_data["url"], timeout=30)
                    with open(output_path, "wb") as f:
                        f.write(img_resp.content)
                    return output_path

    except Exception as e:
        print(f"[Creator] AI image failed: {e}")

    # Fallback: create text image
    return _create_text_image(scene_text, output_path, config.resolution)


def _create_text_image(text: str, output_path: str, resolution: str) -> str:
    """Create a styled text-on-gradient image as fallback."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        w, h = [int(x) for x in resolution.split("x")]

        # Dark gradient background
        img = Image.new("RGB", (w, h), (20, 20, 30))
        draw = ImageDraw.Draw(img)

        # Try to use a nice font
        try:
            font = ImageFont.truetype("segoeui.ttf", 36)
        except OSError:
            font = ImageFont.load_default()

        # Wrap text
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if len(test) > 35:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)

        # Draw centered text
        y_start = h // 2 - len(lines) * 25
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (w - tw) // 2
            draw.text((x, y_start + i * 50), line, fill=(240, 240, 240), font=font)

        img.save(output_path, quality=95)
        return output_path

    except ImportError:
        # No PIL, create blank
        return ""


def _add_background_music(
    video_path: str,
    music_path: str,
    output_path: str,
    volume: float = 0.2,
    fade: bool = True,
) -> str:
    """Add background music to video, mixed with existing audio."""
    from engine.modules.ffmpeg_utils import run_ffprobe

    # Get video duration
    data = run_ffprobe(["-show_format", video_path])
    vid_dur = float(data.get("format", {}).get("duration", 0))

    # Build audio filter
    music_filter = f"[1:a]volume={volume}"
    if fade and vid_dur > 3:
        music_filter += f",afade=t=in:st=0:d=2,afade=t=out:st={vid_dur-2}:d=2"
    music_filter += "[music]"

    # Mix original audio + music
    filter_complex = f"{music_filter};[0:a][music]amix=inputs=2:duration=first[aout]"

    run_ffmpeg([
        "-i", video_path,
        "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(vid_dur),
        "-y", output_path,
    ])

    return output_path


def _generate_srt_from_scenes(scenes: list[Scene], output_path: str) -> str:
    """Generate SRT subtitle file from scenes with timing."""
    current_time = 0.0
    lines = []

    for scene in scenes:
        if not scene.text.strip():
            continue

        start = current_time
        end = current_time + scene.duration

        # Format timestamps
        start_str = _format_srt_time(start)
        end_str = _format_srt_time(end)

        lines.append(f"{scene.index}")
        lines.append(f"{start_str} --> {end_str}")
        lines.append(scene.text)
        lines.append("")

        current_time = end

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


def _format_srt_time(seconds: float) -> str:
    """Format seconds to SRT timestamp: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
