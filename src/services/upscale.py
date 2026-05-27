"""
Video Reup Studio Rebuild — Upscale Service
Uses Real-ESRGAN 4x-UltraSharp for image/video upscaling.
Learned from NAVTools upscale_page.py.
"""

import os
import shutil
import tempfile
from typing import Optional

# Lazy import — engine.modules requires path setup
def _get_ffmpeg_utils():
    import sys
    from config.constants import PROJECT_ROOT
    engine_path = os.path.join(PROJECT_ROOT, 'src', 'engine')
    modules_path = os.path.join(engine_path, 'modules')
    for p in [os.path.join(PROJECT_ROOT, 'src'), engine_path, modules_path]:
        if p not in sys.path:
            sys.path.insert(0, p)
    from engine.modules.ffmpeg_utils import run_ffmpeg, get_video_info
    return run_ffmpeg, get_video_info


# Target resolutions
UPSCALE_TARGETS = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
    "2160p": (3840, 2160),
}


def upscale_image(
    image_path: str,
    output_path: str,
    target: str = "1080p",
    scale: int = 4,
) -> str:
    """
    Upscale image using Real-ESRGAN.
    
    Args:
        image_path: Input image
        output_path: Output image
        target: Target resolution key (720p, 1080p, 1440p, 2160p)
        scale: Upscale factor (2 or 4)
    
    Returns:
        Path to upscaled image
    """
    try:
        import numpy as np
        from PIL import Image
        import torch
    except ImportError:
        raise RuntimeError("Required: pip install Pillow numpy torch")

    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    # Determine target size
    target_w, target_h = UPSCALE_TARGETS.get(target, (1920, 1080))

    # Check if upscale needed
    if w >= target_w and h >= target_h:
        print(f"[Upscale] Image already >= {target}, just resizing")
        img_resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        img_resized.save(output_path, quality=95)
        return output_path

    # Try Real-ESRGAN
    try:
        result = _upscale_esrgan(img, scale)
        # Resize to target
        result = result.resize((target_w, target_h), Image.Resampling.LANCZOS)
        result.save(output_path, quality=95)
        print(f"[Upscale] ESRGAN {w}x{h} → {target_w}x{target_h}: {output_path}")
    except Exception as e:
        print(f"[Upscale] ESRGAN failed ({e}), using Lanczos fallback")
        img_resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        img_resized.save(output_path, quality=95)

    return output_path


def upscale_video(
    video_path: str,
    output_path: str,
    target: str = "1080p",
) -> str:
    """
    Upscale video using FFmpeg (lanczos) or frame-by-frame ESRGAN.
    For speed, uses FFmpeg lanczos scaling by default.
    
    Args:
        video_path: Input video
        output_path: Output video
        target: Target resolution
    
    Returns:
        Path to upscaled video
    """
    run_ffmpeg, get_video_info = _get_ffmpeg_utils()
    target_w, target_h = UPSCALE_TARGETS.get(target, (1920, 1080))
    info = get_video_info(video_path)

    if info.width >= target_w and info.height >= target_h:
        print(f"[Upscale] Video already >= {target}, copying")
        shutil.copy2(video_path, output_path)
        return output_path

    print(f"[Upscale] {info.width}x{info.height} → {target_w}x{target_h}")

    # Use FFmpeg lanczos (fast, good quality)
    run_ffmpeg([
        "-i", video_path,
        "-vf", f"scale={target_w}:{target_h}:flags=lanczos",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "slow",
        "-c:a", "copy",
        "-y",
        output_path,
    ])

    print(f"[Upscale] Done: {output_path}")
    return output_path


def _upscale_esrgan(img, scale: int = 4):
    """Upscale using Real-ESRGAN model (tile-based for large images)."""
    import numpy as np
    import torch
    from PIL import Image

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_path = _find_esrgan_model()

    if not model_path:
        raise FileNotFoundError("Real-ESRGAN model not found (4x-UltraSharp.pth)")

    # Load model
    try:
        import spandrel
        model = spandrel.ModelLoader(device=device).load_from_file(model_path).eval()
    except ImportError:
        raise RuntimeError("spandrel required for ESRGAN. Install: pip install spandrel")

    img_np = np.array(img).astype(np.float32) / 255.0
    h, w, c = img_np.shape

    # Tile-based processing for large images
    tile_size = 512 if w * h < 2048 * 2048 else 256
    overlap = 32

    # Process with tiles
    result = _process_tiles(model, img_np, tile_size, overlap, scale, device)

    # Convert back
    result = (result * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(result)


def _process_tiles(model, img_np, tile_size, overlap, scale, device):
    """Process image in tiles to avoid OOM."""
    import numpy as np
    import torch

    h, w, c = img_np.shape
    out_h, out_w = h * scale, w * scale
    output = np.zeros((out_h, out_w, c), dtype=np.float32)
    count = np.zeros((out_h, out_w, 1), dtype=np.float32)

    for y in range(0, h, tile_size - overlap):
        for x in range(0, w, tile_size - overlap):
            # Extract tile
            y_end = min(y + tile_size, h)
            x_end = min(x + tile_size, w)
            tile = img_np[y:y_end, x:x_end]

            # Pad if needed
            pad_h = tile_size - tile.shape[0]
            pad_w = tile_size - tile.shape[1]
            if pad_h > 0 or pad_w > 0:
                tile = np.pad(tile, ((0, pad_h), (0, pad_w), (0, 0)), mode='reflect')

            # Upscale tile
            tile_tensor = torch.from_numpy(tile).permute(2, 0, 1).unsqueeze(0).to(device)
            with torch.no_grad():
                result_tensor = model(tile_tensor)
            result_tile = result_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy()

            # Remove padding from result
            actual_h = (y_end - y) * scale
            actual_w = (x_end - x) * scale
            result_tile = result_tile[:actual_h, :actual_w]

            # Place in output
            oy, ox = y * scale, x * scale
            output[oy:oy+actual_h, ox:ox+actual_w] += result_tile
            count[oy:oy+actual_h, ox:ox+actual_w] += 1

    # Average overlapping regions
    count = np.maximum(count, 1)
    output /= count

    return output


def _find_esrgan_model() -> Optional[str]:
    """Find Real-ESRGAN model file."""
    from config.constants import PROJECT_ROOT, ASSETS_DIR

    candidates = [
        os.path.join(ASSETS_DIR, "models", "4x-UltraSharp.pth"),
        os.path.join(PROJECT_ROOT, "models", "4x-UltraSharp.pth"),
        os.path.expanduser("~/.cache/esrgan/4x-UltraSharp.pth"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python upscale.py <image_or_video> [output] [--target 1080p]")
        sys.exit(1)

    input_path = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
    target = "1080p"

    for i, arg in enumerate(sys.argv):
        if arg == "--target" and i + 1 < len(sys.argv):
            target = sys.argv[i + 1]

    if not output:
        base, ext = os.path.splitext(input_path)
        output = f"{base}_upscaled{ext}"

    if input_path.lower().endswith((".mp4", ".mkv", ".avi", ".mov", ".webm")):
        upscale_video(input_path, output, target=target)
    else:
        upscale_image(input_path, output, target=target)
