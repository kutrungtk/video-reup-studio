"""
Video Reup Studio Rebuild — Background Removal Service
Uses rembg (BiRefNet) for offline background removal.
Learned from NAVTools bg_remove_page.py.
"""

import os
from typing import Optional


# Background color presets
BG_COLORS = {
    "transparent": None,
    "green": (0, 177, 64),
    "blue": (0, 71, 187),
    "red": (234, 51, 35),
    "white": (255, 255, 255),
    "black": (0, 0, 0),
}


def remove_background(
    image_path: str,
    output_path: str,
    bg_color: str = "transparent",
    custom_color: Optional[tuple] = None,
) -> str:
    """
    Remove background from image using BiRefNet (rembg).
    
    Args:
        image_path: Input image path
        output_path: Output image path
        bg_color: Background color preset name or "custom"
        custom_color: (R, G, B) tuple if bg_color="custom"
    
    Returns:
        Path to output image
    """
    try:
        from PIL import Image
        from rembg import remove
    except ImportError:
        raise RuntimeError("Required: pip install rembg Pillow")

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Load and remove background
    img = Image.open(image_path).convert("RGBA")
    result = remove(img)

    # Apply background color
    color = custom_color if bg_color == "custom" else BG_COLORS.get(bg_color)

    if color is not None:
        # Create colored background
        bg = Image.new("RGBA", result.size, (*color, 255))
        bg.paste(result, mask=result.split()[3])  # paste using alpha as mask
        result = bg

    # Save
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    if output_path.lower().endswith(".jpg") or output_path.lower().endswith(".jpeg"):
        result = result.convert("RGB")
    result.save(output_path, quality=95)

    print(f"[BG Remove] Done: {output_path}")
    return output_path


def remove_background_batch(
    image_paths: list[str],
    output_dir: str,
    bg_color: str = "transparent",
    progress_cb=None,
) -> list[str]:
    """
    Remove background from multiple images.
    
    Args:
        image_paths: List of input image paths
        output_dir: Output directory
        bg_color: Background color preset
        progress_cb: Callback(percent, message)
    
    Returns:
        List of output paths
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []
    total = len(image_paths)

    for i, path in enumerate(image_paths):
        fname = os.path.basename(path)
        name, _ = os.path.splitext(fname)
        output_path = os.path.join(output_dir, f"{name}_nobg.png")

        try:
            remove_background(path, output_path, bg_color=bg_color)
            results.append(output_path)
        except Exception as e:
            print(f"[BG Remove] Failed: {fname}: {e}")
            results.append("")

        if progress_cb:
            progress_cb(int((i + 1) / total * 100), f"BG Remove: {i+1}/{total}")

    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python bg_remove.py <image> [output] [--bg green|blue|white|black|transparent]")
        sys.exit(1)

    input_path = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
    bg = "transparent"

    for i, arg in enumerate(sys.argv):
        if arg == "--bg" and i + 1 < len(sys.argv):
            bg = sys.argv[i + 1]

    if not output:
        base, ext = os.path.splitext(input_path)
        output = f"{base}_nobg.png"

    remove_background(input_path, output, bg_color=bg)
