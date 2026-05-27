"""
Video Reup Studio Rebuild — Batch Resize Service
Resize images to platform-specific presets.
Learned from NAVTools batch_resize_page.py.
"""

import os
from typing import Optional, Tuple


# Resize presets (name → (width, height))
PRESETS = {
    "Instagram Post (1080x1080)": (1080, 1080),
    "Instagram Story (1080x1920)": (1080, 1920),
    "YouTube Thumbnail (1280x720)": (1280, 720),
    "TikTok (1080x1920)": (1080, 1920),
    "Facebook Cover (820x312)": (820, 312),
    "Twitter Header (1500x500)": (1500, 500),
    "Wallpaper HD (1920x1080)": (1920, 1080),
    "Wallpaper 4K (3840x2160)": (3840, 2160),
}

# Resize modes
MODES = ["fit", "pad", "stretch"]


def resize_image(
    image_path: str,
    output_path: str,
    size: Tuple[int, int],
    mode: str = "fit",
    bg_color: Tuple[int, int, int] = (0, 0, 0),
) -> str:
    """
    Resize single image.
    
    Args:
        image_path: Input image
        output_path: Output image
        size: (width, height) target
        mode: "fit" (crop center), "pad" (add borders), "stretch" (distort)
        bg_color: Background color for padding
    
    Returns:
        Output path
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise RuntimeError("Required: pip install Pillow")

    img = Image.open(image_path)
    target_w, target_h = size

    if mode == "fit":
        # Crop to fill (center crop)
        img = ImageOps.fit(img, (target_w, target_h), method=Image.Resampling.LANCZOS)
    elif mode == "pad":
        # Resize to fit within bounds, pad remaining space
        img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
        padded = Image.new("RGB", (target_w, target_h), bg_color)
        x = (target_w - img.width) // 2
        y = (target_h - img.height) // 2
        padded.paste(img, (x, y))
        img = padded
    elif mode == "stretch":
        # Stretch to exact size (may distort)
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    # Save
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    if img.mode == "RGBA" and output_path.lower().endswith((".jpg", ".jpeg")):
        img = img.convert("RGB")
    img.save(output_path, quality=95)

    return output_path


def resize_batch(
    image_paths: list[str],
    output_dir: str,
    size: Tuple[int, int],
    mode: str = "fit",
    output_format: str = "keep",
    progress_cb=None,
) -> list[str]:
    """
    Resize multiple images.
    
    Args:
        image_paths: List of input paths
        output_dir: Output directory
        size: Target (width, height)
        mode: Resize mode
        output_format: "keep" (same as input), "png", "jpg"
        progress_cb: Callback(percent, message)
    
    Returns:
        List of output paths
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []
    total = len(image_paths)

    for i, path in enumerate(image_paths):
        fname = os.path.basename(path)
        name, ext = os.path.splitext(fname)

        if output_format == "png":
            ext = ".png"
        elif output_format == "jpg":
            ext = ".jpg"

        output_path = os.path.join(output_dir, f"{name}_resized{ext}")

        try:
            resize_image(path, output_path, size, mode=mode)
            results.append(output_path)
        except Exception as e:
            print(f"[Resize] Failed: {fname}: {e}")
            results.append("")

        if progress_cb:
            progress_cb(int((i + 1) / total * 100), f"Resize: {i+1}/{total}")

    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python batch_resize.py <image> [output] [--size 1080x1920] [--mode fit|pad|stretch]")
        print(f"Presets: {list(PRESETS.keys())}")
        sys.exit(1)

    input_path = sys.argv[1]
    output = None
    size = (1080, 1920)
    mode = "fit"

    for i, arg in enumerate(sys.argv):
        if arg == "--size" and i + 1 < len(sys.argv):
            w, h = sys.argv[i + 1].split("x")
            size = (int(w), int(h))
        elif arg == "--mode" and i + 1 < len(sys.argv):
            mode = sys.argv[i + 1]
        elif i == 2 and not arg.startswith("--"):
            output = arg

    if not output:
        base, ext = os.path.splitext(input_path)
        output = f"{base}_{size[0]}x{size[1]}{ext}"

    resize_image(input_path, output, size, mode=mode)
    print(f"Output: {output}")
