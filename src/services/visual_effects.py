"""
Video Reup Studio Rebuild — Visual Effects Service
Multiple effects for creating video from static images.
Beyond Ken Burns: zoom, pan, parallax, slide, rotate, pulse, etc.

All effects use FFmpeg filters — no AI needed, runs locally.
"""

import os
import random
from typing import Optional

from engine.modules.ffmpeg_utils import run_ffmpeg


# Available effects
EFFECTS = {
    "zoom_in": "Zoom in slowly (Ken Burns classic)",
    "zoom_out": "Zoom out slowly (reveal)",
    "pan_left": "Pan from right to left",
    "pan_right": "Pan from left to right",
    "pan_up": "Pan from bottom to top",
    "pan_down": "Pan from top to bottom",
    "zoom_pan_tl": "Zoom + pan to top-left",
    "zoom_pan_br": "Zoom + pan to bottom-right",
    "parallax": "Fake parallax (zoom + slight pan)",
    "slide_left": "Slide in from right",
    "slide_right": "Slide in from left",
    "rotate_cw": "Slow clockwise rotation",
    "rotate_ccw": "Slow counter-clockwise rotation",
    "pulse": "Subtle zoom pulse (breathe effect)",
    "static": "No movement (static image)",
    "random": "Random effect from above",
}

# Camera move descriptions for AI prompt generation
CAMERA_MOVES_FOR_PROMPT = [
    "static tripod shot",
    "slow dolly-in",
    "slow dolly-out",
    "tracking shot left to right",
    "tracking shot right to left",
    "crane shot rising up",
    "crane shot descending",
    "orbit shot around subject",
    "pull-back reveal",
    "push-in close-up",
    "tilt up from ground",
    "tilt down from sky",
    "handheld subtle movement",
    "FPV drone forward",
    "zoom in gradually",
    "zoom out gradually",
]


def image_to_video(
    image_path: str,
    output_path: str,
    duration: float = 5.0,
    effect: str = "zoom_in",
    resolution: str = "1080x1920",
    fps: int = 30,
) -> str:
    """
    Create video from static image with motion effect.
    
    Args:
        image_path: Input image path
        output_path: Output video path
        duration: Video duration in seconds
        effect: Effect name (see EFFECTS dict)
        resolution: Output resolution WxH
        fps: Frames per second
    
    Returns:
        Path to output video
    """
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    if effect == "random":
        effect = random.choice([k for k in EFFECTS.keys() if k not in ("random", "static")])

    w, h = [int(x) for x in resolution.split("x")]
    total_frames = int(duration * fps)

    # Build zoompan filter based on effect
    zp_filter = _get_zoompan_filter(effect, w, h, total_frames, fps, duration)

    args = [
        "-loop", "1",
        "-i", image_path,
        "-vf", zp_filter,
        "-t", str(duration),
        "-c:v", "libx264",
        "-crf", "20",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-y",
        output_path,
    ]

    run_ffmpeg(args)
    return output_path


def image_to_video_batch(
    images: list[dict],
    output_dir: str,
    resolution: str = "1080x1920",
    fps: int = 30,
    progress_cb=None,
) -> list[str]:
    """
    Create videos from multiple images with varied effects.
    
    Args:
        images: List of {"path": str, "duration": float, "effect": str}
        output_dir: Output directory
        resolution: Output resolution
        fps: FPS
        progress_cb: Callback(percent, message)
    
    Returns:
        List of output video paths
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []
    total = len(images)

    # Cycle through effects for variety
    effect_cycle = [k for k in EFFECTS.keys() if k not in ("random", "static")]

    for i, img_info in enumerate(images):
        path = img_info["path"]
        duration = img_info.get("duration", 5.0)
        effect = img_info.get("effect", effect_cycle[i % len(effect_cycle)])

        output_path = os.path.join(output_dir, f"scene_{i+1:03d}.mp4")

        try:
            image_to_video(path, output_path, duration, effect, resolution, fps)
            results.append(output_path)
        except Exception as e:
            print(f"[Effects] Failed scene {i+1}: {e}")
            results.append("")

        if progress_cb:
            progress_cb(int((i + 1) / total * 100), f"Visual {i+1}/{total}: {effect}")

    return results


def _get_zoompan_filter(effect: str, w: int, h: int, frames: int, fps: int, duration: float) -> str:
    """Build FFmpeg zoompan filter string for given effect."""
    # zoompan: z=zoom, x=pan_x, y=pan_y, d=duration_frames, s=output_size, fps=fps
    d = frames
    s = f"{w}x{h}"

    if effect == "zoom_in":
        # Zoom from 1.0 to 1.3
        return f"zoompan=z='min(1.3,1+0.3*on/{d})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={s}:fps={fps}"

    elif effect == "zoom_out":
        # Zoom from 1.3 to 1.0
        return f"zoompan=z='max(1.0,1.3-0.3*on/{d})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={s}:fps={fps}"

    elif effect == "pan_left":
        # Pan from right to left
        return f"zoompan=z='1.1':x='iw*(1-on/{d})*0.1':y='ih/2-(ih/zoom/2)':d={d}:s={s}:fps={fps}"

    elif effect == "pan_right":
        # Pan from left to right
        return f"zoompan=z='1.1':x='iw*on/{d}*0.1':y='ih/2-(ih/zoom/2)':d={d}:s={s}:fps={fps}"

    elif effect == "pan_up":
        # Pan from bottom to top
        return f"zoompan=z='1.1':x='iw/2-(iw/zoom/2)':y='ih*(1-on/{d})*0.1':d={d}:s={s}:fps={fps}"

    elif effect == "pan_down":
        # Pan from top to bottom
        return f"zoompan=z='1.1':x='iw/2-(iw/zoom/2)':y='ih*on/{d}*0.1':d={d}:s={s}:fps={fps}"

    elif effect == "zoom_pan_tl":
        # Zoom in + pan to top-left
        return f"zoompan=z='min(1.4,1+0.4*on/{d})':x='iw*0.1*(1-on/{d})':y='ih*0.1*(1-on/{d})':d={d}:s={s}:fps={fps}"

    elif effect == "zoom_pan_br":
        # Zoom in + pan to bottom-right
        return f"zoompan=z='min(1.4,1+0.4*on/{d})':x='iw*0.1*on/{d}':y='ih*0.1*on/{d}':d={d}:s={s}:fps={fps}"

    elif effect == "parallax":
        # Fake parallax: zoom + slight horizontal pan
        return f"zoompan=z='min(1.2,1+0.2*on/{d})':x='iw*0.05*sin(on/{d}*3.14)':y='ih/2-(ih/zoom/2)':d={d}:s={s}:fps={fps}"

    elif effect == "slide_left":
        # Slide from right edge to center
        return f"zoompan=z='1.0':x='iw*0.2*(1-on/{d})':y='0':d={d}:s={s}:fps={fps}"

    elif effect == "slide_right":
        # Slide from left edge to center
        return f"zoompan=z='1.0':x='-iw*0.2*(1-on/{d})':y='0':d={d}:s={s}:fps={fps}"

    elif effect == "rotate_cw":
        # Slow clockwise rotation (via zoompan + slight pan)
        return f"zoompan=z='1.15':x='iw/2-(iw/zoom/2)+iw*0.03*sin(on/{d}*6.28)':y='ih/2-(ih/zoom/2)+ih*0.03*cos(on/{d}*6.28)':d={d}:s={s}:fps={fps}"

    elif effect == "rotate_ccw":
        # Counter-clockwise
        return f"zoompan=z='1.15':x='iw/2-(iw/zoom/2)-iw*0.03*sin(on/{d}*6.28)':y='ih/2-(ih/zoom/2)-ih*0.03*cos(on/{d}*6.28)':d={d}:s={s}:fps={fps}"

    elif effect == "pulse":
        # Subtle zoom pulse (breathe)
        return f"zoompan=z='1.05+0.05*sin(on/{d}*6.28*2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={s}:fps={fps}"

    else:
        # Static — no movement
        return f"zoompan=z='1.0':x='0':y='0':d={d}:s={s}:fps={fps}"


def get_random_camera_move() -> str:
    """Get random camera move description for AI prompt."""
    return random.choice(CAMERA_MOVES_FOR_PROMPT)


def build_visual_prompt(scene_text: str, style: str = "cinematic") -> str:
    """
    Build AI image generation prompt with camera move suggestion.
    Used when generating images for Creator page scenes.
    """
    camera = get_random_camera_move()
    return (
        f"{style}, {camera}, dramatic lighting, ultra HD 4K, "
        f"vertical 9:16 portrait orientation, no text in image. "
        f"Scene: {scene_text}"
    )


if __name__ == "__main__":
    import sys
    print("Visual Effects — Available effects:")
    for name, desc in EFFECTS.items():
        print(f"  {name:15s} — {desc}")
    print(f"\nCamera moves for AI prompts: {len(CAMERA_MOVES_FOR_PROMPT)} options")

    if len(sys.argv) >= 3:
        img = sys.argv[1]
        out = sys.argv[2]
        effect = sys.argv[3] if len(sys.argv) > 3 else "random"
        dur = float(sys.argv[4]) if len(sys.argv) > 4 else 5.0
        image_to_video(img, out, duration=dur, effect=effect)
        print(f"Created: {out} ({effect}, {dur}s)")
