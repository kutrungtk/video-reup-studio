"""
Video Reup Studio - Batch Runner
Run pipeline_v2 for multiple URLs sequentially.
Outputs progress per-video for GUI consumption.
"""

import json
import os
import time
from typing import Optional
from pathlib import Path

from pipeline_v2 import PipelineConfig, PipelineV2


def run_batch(
    urls: list[str],
    base_output_dir: str,
    target_language: str = "it",
    split_platform: str = "tiktok",
    voice_engine: str = "edge-tts",
    cookies_path: str = "",
    **kwargs,
) -> list[dict]:
    """
    Run pipeline for multiple URLs sequentially.
    
    Args:
        urls: List of YouTube URLs or local video paths
        base_output_dir: Base directory (each video gets a subfolder)
        target_language: Target language code
        split_platform: Platform for split/export
        voice_engine: TTS engine to use
        cookies_path: Path to cookies.txt
        **kwargs: Additional PipelineConfig fields
    
    Returns:
        List of summary dicts (one per video)
    """
    results = []
    total = len(urls)
    start_time = time.time()

    _batch_progress("batch_start", 0, total, f"Starting batch: {total} videos")

    for i, url in enumerate(urls, 1):
        url = url.strip()
        if not url:
            continue

        # Generate project folder name
        video_name = _url_to_name(url, i)
        project_dir = os.path.join(base_output_dir, video_name)

        _batch_progress("video_start", i, total, f"[{i}/{total}] Starting: {url[:60]}...")

        try:
            # Build config for this video
            config = PipelineConfig(
                youtube_url=url if url.startswith("http") else "",
                input_path=url if not url.startswith("http") else "",
                output_dir=project_dir,
                target_language=target_language,
                split_platform=split_platform,
                voice_engine=voice_engine,
                cookies_path=cookies_path,
                **{k: v for k, v in kwargs.items() if k in PipelineConfig.__dataclass_fields__},
            )

            # Run pipeline
            pipeline = PipelineV2(config)
            summary = pipeline.run()
            summary["batch_index"] = i
            summary["url"] = url
            results.append(summary)

            _batch_progress("video_done", i, total, 
                           f"[{i}/{total}] Done: {summary.get('total_parts', 0)} parts in {summary.get('elapsed_seconds', 0)}s")

        except Exception as e:
            error_result = {
                "status": "error",
                "batch_index": i,
                "url": url,
                "error": str(e),
            }
            results.append(error_result)
            _batch_progress("video_error", i, total, f"[{i}/{total}] Error: {str(e)[:100]}")

    # Batch complete
    elapsed = time.time() - start_time
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = sum(1 for r in results if r.get("status") == "error")

    _batch_progress("batch_done", total, total,
                    f"Batch complete: {success_count} success, {error_count} errors, {elapsed:.0f}s total")

    # Save batch summary
    batch_summary = {
        "total_videos": total,
        "success": success_count,
        "errors": error_count,
        "elapsed_seconds": round(elapsed, 1),
        "results": results,
    }
    summary_path = os.path.join(base_output_dir, "batch_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(batch_summary, f, indent=2, ensure_ascii=False)

    return results


def _url_to_name(url: str, index: int) -> str:
    """Generate a folder name from URL or path."""
    from datetime import datetime
    date = datetime.now().strftime("%Y-%m-%d")

    if url.startswith("http"):
        # Extract video ID or use index
        if "youtube.com" in url or "youtu.be" in url:
            # Try to get video ID
            if "v=" in url:
                vid = url.split("v=")[1].split("&")[0][:11]
            elif "youtu.be/" in url:
                vid = url.split("youtu.be/")[1].split("?")[0][:11]
            else:
                vid = f"video_{index:03d}"
            return f"{date}_{vid}"
        else:
            return f"{date}_video_{index:03d}"
    else:
        # Local file — use filename
        stem = Path(url).stem.replace(" ", "_")[:30]
        return f"{date}_{stem}"


def _batch_progress(event: str, current: int, total: int, message: str):
    """Output batch progress as JSON line."""
    progress = {
        "type": "batch_progress",
        "event": event,
        "current": current,
        "total": total,
        "percent": round((current / total) * 100) if total > 0 else 0,
        "message": message,
        "timestamp": time.time(),
    }
    print(json.dumps(progress, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python batch_runner.py <urls_file_or_json_config>")
        print("  urls_file: one URL per line")
        print("  json_config: {urls: [...], target_language: 'it', ...}")
        sys.exit(1)

    input_file = sys.argv[1]

    if input_file.endswith(".json"):
        # JSON config mode
        with open(input_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        urls = config.pop("urls", [])
        base_dir = config.pop("output_dir", "batch_output")
        results = run_batch(urls, base_dir, **config)
    else:
        # Simple URL list mode
        with open(input_file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "batch_output"
        results = run_batch(urls, output_dir)

    print(f"\n{'='*50}")
    print(f"Batch complete: {len(results)} videos processed")
    for r in results:
        status = "✅" if r.get("status") == "success" else "❌"
        print(f"  {status} [{r.get('batch_index')}] {r.get('url', '')[:50]}")
