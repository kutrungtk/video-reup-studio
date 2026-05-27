"""
Video Reup Studio Rebuild — Watermark Removal Service
Uses LaMa inpainting model to remove watermarks from video/images.
Learned from NAVTools inpaint_lama.py.
"""

import os
import shutil
import tempfile
from typing import Optional, Tuple

# Lazy import — engine.modules requires path setup
def _get_ffmpeg_utils():
    import sys
    from config.constants import PROJECT_ROOT
    engine_path = os.path.join(PROJECT_ROOT, 'src', 'engine')
    modules_path = os.path.join(engine_path, 'modules')
    for p in [os.path.join(PROJECT_ROOT, 'src'), engine_path, modules_path]:
        if p not in sys.path:
            sys.path.insert(0, p)
    from engine.modules.ffmpeg_utils import run_ffmpeg, run_ffprobe, get_video_info
    return run_ffmpeg, run_ffprobe, get_video_info


def remove_watermark_image(
    image_path: str,
    output_path: str,
    region: Optional[Tuple[int, int, int, int]] = None,
    auto_detect: bool = True,
) -> str:
    """
    Remove watermark from a single image using LaMa inpainting.
    
    Args:
        image_path: Input image path
        output_path: Output image path
        region: (x, y, width, height) of watermark area. None = auto-detect
        auto_detect: If True and region is None, detect watermark in bottom-right corner
    
    Returns:
        Path to output image
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        raise RuntimeError("PIL/numpy required. Install: pip install Pillow numpy")

    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    # Determine watermark region
    if region is None and auto_detect:
        # Default: bottom-right corner (common for Veo/TikTok watermarks)
        # ~15% width, ~8% height from bottom-right
        rw = int(w * 0.15)
        rh = int(h * 0.08)
        region = (w - rw - 10, h - rh - 10, rw, rh)

    if region is None:
        # No region specified, just copy
        img.save(output_path)
        return output_path

    x, y, rw, rh = region

    # Create mask (white = area to inpaint)
    mask = Image.new("L", (w, h), 0)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(mask)
    # Add padding around region
    pad = 5
    draw.rectangle([x - pad, y - pad, x + rw + pad, y + rh + pad], fill=255)

    # Try LaMa model
    try:
        result = _inpaint_lama(img, mask)
        result.save(output_path)
        print(f"[Watermark] LaMa inpaint OK: {output_path}")
    except Exception as e:
        print(f"[Watermark] LaMa failed ({e}), using simple fill fallback")
        result = _inpaint_simple(img, mask, x, y, rw, rh)
        result.save(output_path)

    return output_path


def remove_watermark_video(
    video_path: str,
    output_path: str,
    region: Optional[Tuple[int, int, int, int]] = None,
    auto_detect: bool = True,
) -> str:
    """
    Remove watermark from video by processing each frame.
    
    Args:
        video_path: Input video path
        output_path: Output video path
        region: (x, y, w, h) watermark area
        auto_detect: Auto-detect bottom-right corner
    
    Returns:
        Path to output video
    """
    run_ffmpeg, run_ffprobe, get_video_info = _get_ffmpeg_utils()
    info = get_video_info(video_path)

    # Create temp dir for frames
    temp_dir = tempfile.mkdtemp(prefix="vrs_wm_")
    frames_dir = os.path.join(temp_dir, "frames")
    clean_dir = os.path.join(temp_dir, "clean")
    os.makedirs(frames_dir)
    os.makedirs(clean_dir)

    try:
        # Extract frames
        print(f"[Watermark] Extracting frames from {video_path}...")
        run_ffmpeg([
            "-i", video_path,
            "-qscale:v", "2",
            os.path.join(frames_dir, "%08d.png"),
            "-y",
        ])

        # Process each frame
        frames = sorted(os.listdir(frames_dir))
        total = len(frames)
        print(f"[Watermark] Processing {total} frames...")

        for i, fname in enumerate(frames):
            src = os.path.join(frames_dir, fname)
            dst = os.path.join(clean_dir, fname)
            remove_watermark_image(src, dst, region=region, auto_detect=auto_detect)
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{total}] frames processed")

        # Re-encode video from clean frames
        print(f"[Watermark] Encoding clean video...")
        run_ffmpeg([
            "-y",
            "-framerate", str(info.fps),
            "-i", os.path.join(clean_dir, "%08d.png"),
            "-i", video_path,
            "-map", "0:v:0",
            "-map", "1:a?",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-crf", "20",
            "-preset", "fast",
            "-c:a", "copy",
            output_path,
        ])

        print(f"[Watermark] Done: {output_path}")
        return output_path

    finally:
        # Cleanup temp
        shutil.rmtree(temp_dir, ignore_errors=True)


def _inpaint_lama(img, mask):
    """Inpaint using LaMa model (requires torch + model file)."""
    import numpy as np

    try:
        import torch
        # Try loading LaMa model
        model_path = _find_lama_model()
        if not model_path:
            raise FileNotFoundError("LaMa model not found")

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Load model
        try:
            import spandrel
            model = spandrel.ModelLoader(device=device).load_from_file(model_path)
        except ImportError:
            model = torch.jit.load(model_path, map_location=device)

        # Prepare tensors
        img_np = np.array(img).astype(np.float32) / 255.0
        mask_np = np.array(mask).astype(np.float32) / 255.0

        img_tensor = torch.from_numpy(img_np).permute(2, 0, 1).unsqueeze(0).to(device)
        mask_tensor = torch.from_numpy(mask_np).unsqueeze(0).unsqueeze(0).to(device)

        # Inpaint
        with torch.no_grad():
            if hasattr(model, '__call__'):
                result = model(img_tensor, mask_tensor)
            else:
                result = model.forward(img_tensor, mask_tensor)

        # Convert back to PIL
        result_np = result.squeeze(0).permute(1, 2, 0).cpu().numpy()
        result_np = (result_np * 255).clip(0, 255).astype(np.uint8)

        from PIL import Image
        return Image.fromarray(result_np)

    except (ImportError, FileNotFoundError) as e:
        raise RuntimeError(f"LaMa not available: {e}")


def _inpaint_simple(img, mask, x, y, w, h):
    """Simple inpainting fallback — fill with surrounding color."""
    import numpy as np
    from PIL import Image, ImageFilter

    img_np = np.array(img)
    mask_np = np.array(mask)

    # Sample surrounding pixels for fill color
    pad = 20
    top_strip = img_np[max(0, y-pad):y, x:x+w]
    left_strip = img_np[y:y+h, max(0, x-pad):x]

    if top_strip.size > 0:
        fill_color = top_strip.mean(axis=(0, 1)).astype(np.uint8)
    elif left_strip.size > 0:
        fill_color = left_strip.mean(axis=(0, 1)).astype(np.uint8)
    else:
        fill_color = np.array([0, 0, 0], dtype=np.uint8)

    # Fill masked area
    mask_bool = mask_np > 128
    img_np[mask_bool] = fill_color

    # Blur the filled area for smoother blend
    result = Image.fromarray(img_np)
    blurred = result.filter(ImageFilter.GaussianBlur(radius=3))

    # Composite: use blurred only in mask area
    result_np = np.array(result)
    blurred_np = np.array(blurred)

    # Feather mask edges
    from PIL import ImageFilter as IF
    mask_feathered = Image.fromarray(mask_np).filter(IF.GaussianBlur(radius=5))
    feather_np = np.array(mask_feathered).astype(np.float32) / 255.0

    # Blend
    for c in range(3):
        result_np[:, :, c] = (
            result_np[:, :, c] * (1 - feather_np) +
            blurred_np[:, :, c] * feather_np
        ).astype(np.uint8)

    return Image.fromarray(result_np)


def _find_lama_model() -> Optional[str]:
    """Find LaMa model file."""
    from config.constants import PROJECT_ROOT, ASSETS_DIR

    # Check common locations
    candidates = [
        os.path.join(ASSETS_DIR, "models", "big-lama.pt"),
        os.path.join(PROJECT_ROOT, "models", "big-lama.pt"),
        os.path.expanduser("~/.cache/lama/big-lama.pt"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python watermark_remove.py <image_or_video> [output] [--region x,y,w,h]")
        sys.exit(1)

    input_path = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else input_path.replace(".", "_clean.")

    region = None
    for i, arg in enumerate(sys.argv):
        if arg == "--region" and i + 1 < len(sys.argv):
            parts = sys.argv[i + 1].split(",")
            region = tuple(int(p) for p in parts)

    if input_path.lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".webm")):
        remove_watermark_video(input_path, output, region=region)
    else:
        remove_watermark_image(input_path, output, region=region)
