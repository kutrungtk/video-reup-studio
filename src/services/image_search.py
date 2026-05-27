"""
Video Reup Studio Rebuild — Image Search & Reference Service
Search and download reference images from web sources.
Supports: Google Images (via scraping), Unsplash, Pexels (free APIs).
"""

import os
import re
import json
import time
import hashlib
import urllib.request
import urllib.parse
from typing import Optional


def search_google_images(
    query: str,
    output_dir: str,
    count: int = 5,
    safe: bool = True,
) -> list[str]:
    """
    Search for images — tries multiple sources in order:
    1. Pexels API (free, reliable, 200 req/hour)
    2. Google Images scraping (unreliable, often blocked)
    
    Args:
        query: Search query
        output_dir: Directory to save images
        count: Number of images to download
        safe: Safe search enabled
    
    Returns:
        List of downloaded image paths
    """
    os.makedirs(output_dir, exist_ok=True)

    # Try Pexels first (reliable)
    from config.settings import get_settings
    settings = get_settings()
    pexels_key = settings.get("pexels_api_key") or ""
    if pexels_key:
        results = _search_pexels_direct(query, output_dir, count, pexels_key)
        if results:
            return results

    # Fallback: Google scraping (often blocked)
    results = _scrape_google_images(query, output_dir, count, safe)
    if results:
        return results

    # Last resort: DuckDuckGo (no API key needed)
    results = _search_duckduckgo(query, output_dir, count)
    return results


def _search_pexels_direct(query: str, output_dir: str, count: int, api_key: str) -> list[str]:
    """Search Pexels API — free, reliable, high quality stock photos."""
    try:
        url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page={count}&orientation=portrait"
        req = urllib.request.Request(url, headers={"Authorization": api_key})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        downloaded = []
        for i, photo in enumerate(data.get("photos", [])):
            img_url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large", "")
            if not img_url:
                continue

            filename = f"pexels_{i+1:03d}.jpg"
            filepath = os.path.join(output_dir, filename)

            try:
                headers_dl = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}
                req_dl = urllib.request.Request(img_url, headers=headers_dl)
                with urllib.request.urlopen(req_dl, timeout=15) as img_resp:
                    img_data = img_resp.read()
                if len(img_data) > 5000:
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    downloaded.append(filepath)
                    print(f"  [Pexels] Downloaded: {filename} ({len(img_data)//1024}KB)")
            except Exception:
                continue

            if len(downloaded) >= count:
                break

        print(f"[Search] Pexels: {len(downloaded)}/{count} images for: {query}")
        return downloaded

    except Exception as e:
        print(f"[Search] Pexels failed: {e}")
        return []


def _search_duckduckgo(query: str, output_dir: str, count: int) -> list[str]:
    """Search DuckDuckGo images — no API key needed, less likely to block."""
    try:
        # DuckDuckGo image search via their instant answer API
        params = urllib.parse.urlencode({
            "q": query,
            "t": "ht",
            "iax": "images",
            "ia": "images",
        })
        url = f"https://duckduckgo.com/?{params}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        # Use vqd token approach
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Extract vqd token
        vqd_match = re.search(r'vqd=["\']([^"\']+)', html)
        if not vqd_match:
            return []

        vqd = vqd_match.group(1)

        # Fetch image results
        img_url = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={urllib.parse.quote(query)}&vqd={vqd}&f=,,,,,&p=1"
        req2 = urllib.request.Request(img_url, headers=headers)
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            data = json.loads(resp2.read())

        downloaded = []
        for i, result in enumerate(data.get("results", [])):
            img_src = result.get("image", "")
            if not img_src:
                continue

            filename = f"ddg_{i+1:03d}.jpg"
            filepath = os.path.join(output_dir, filename)

            try:
                req_dl = urllib.request.Request(img_src, headers=headers)
                with urllib.request.urlopen(req_dl, timeout=10) as img_resp:
                    img_data = img_resp.read()
                if len(img_data) > 5000:
                    with open(filepath, "wb") as f:
                        f.write(img_data)
                    downloaded.append(filepath)
            except Exception:
                continue

            if len(downloaded) >= count:
                break

        print(f"[Search] DuckDuckGo: {len(downloaded)}/{count} images for: {query}")
        return downloaded

    except Exception as e:
        print(f"[Search] DuckDuckGo failed: {e}")
        return []


def _scrape_google_images(
    query: str,
    output_dir: str,
    count: int = 5,
    safe: bool = True,
) -> list[str]:
    """
    Scrape Google Images (unreliable — Google often blocks).
    Kept as fallback only.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Build Google Images search URL
    params = urllib.parse.urlencode({
        "q": query,
        "tbm": "isch",
        "safe": "active" if safe else "off",
    })
    url = f"https://www.google.com/search?{params}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Extract image URLs from HTML
        # Google embeds image URLs in various formats
        image_urls = []

        # Pattern 1: data-src or src in img tags
        patterns = [
            r'"(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
            r'data-src="(https?://[^"]+)"',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html)
            for m in matches:
                if "gstatic" not in m and "google" not in m and len(m) > 50:
                    image_urls.append(m)

        # Deduplicate
        image_urls = list(dict.fromkeys(image_urls))[:count * 2]

        # Download images
        downloaded = []
        for i, img_url in enumerate(image_urls):
            if len(downloaded) >= count:
                break

            try:
                ext = _get_extension(img_url)
                filename = f"ref_{i+1:03d}{ext}"
                filepath = os.path.join(output_dir, filename)

                req = urllib.request.Request(img_url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()

                if len(data) > 5000:  # Skip tiny images
                    with open(filepath, "wb") as f:
                        f.write(data)
                    downloaded.append(filepath)
                    print(f"  [Search] Downloaded: {filename} ({len(data)//1024}KB)")

            except Exception:
                continue

            time.sleep(0.3)  # Rate limit

        print(f"[Search] Downloaded {len(downloaded)}/{count} images for: {query}")
        return downloaded

    except Exception as e:
        print(f"[Search] Google search failed: {e}")
        return []


def search_unsplash(
    query: str,
    output_dir: str,
    count: int = 5,
    api_key: str = "",
) -> list[str]:
    """
    Search Unsplash for free stock photos.
    Requires Unsplash API key (free tier: 50 req/hour).
    """
    if not api_key:
        print("[Search] Unsplash API key not set, skipping")
        return []

    os.makedirs(output_dir, exist_ok=True)

    url = f"https://api.unsplash.com/search/photos?query={urllib.parse.quote(query)}&per_page={count}"
    headers = {"Authorization": f"Client-ID {api_key}"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        downloaded = []
        for i, photo in enumerate(data.get("results", [])):
            img_url = photo.get("urls", {}).get("regular", "")
            if not img_url:
                continue

            filename = f"unsplash_{i+1:03d}.jpg"
            filepath = os.path.join(output_dir, filename)

            try:
                urllib.request.urlretrieve(img_url, filepath)
                downloaded.append(filepath)
            except Exception:
                continue

        return downloaded

    except Exception as e:
        print(f"[Search] Unsplash failed: {e}")
        return []


def search_pexels(
    query: str,
    output_dir: str,
    count: int = 5,
    api_key: str = "",
) -> list[str]:
    """
    Search Pexels for free stock photos/videos.
    Requires Pexels API key (free, generous limits).
    """
    if not api_key:
        print("[Search] Pexels API key not set, skipping")
        return []

    os.makedirs(output_dir, exist_ok=True)

    url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page={count}"
    headers = {"Authorization": api_key}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        downloaded = []
        for i, photo in enumerate(data.get("photos", [])):
            img_url = photo.get("src", {}).get("large", "")
            if not img_url:
                continue

            filename = f"pexels_{i+1:03d}.jpg"
            filepath = os.path.join(output_dir, filename)

            try:
                urllib.request.urlretrieve(img_url, filepath)
                downloaded.append(filepath)
            except Exception:
                continue

        return downloaded

    except Exception as e:
        print(f"[Search] Pexels failed: {e}")
        return []


def search_reference_images(
    query: str,
    output_dir: str,
    count: int = 5,
    sources: list[str] = None,
) -> list[str]:
    """
    Search multiple sources for reference images.
    
    Args:
        query: Search query
        output_dir: Output directory
        count: Images per source
        sources: List of sources to try ["google", "unsplash", "pexels"]
    
    Returns:
        All downloaded image paths
    """
    if sources is None:
        sources = ["google"]  # Default: Google only (no API key needed)

    from config.settings import get_settings
    settings = get_settings()

    all_images = []

    for source in sources:
        if source == "google":
            images = search_google_images(query, output_dir, count)
            all_images.extend(images)
        elif source == "unsplash":
            key = settings.get("unsplash_api_key")
            images = search_unsplash(query, output_dir, count, api_key=key)
            all_images.extend(images)
        elif source == "pexels":
            key = settings.get("pexels_api_key")
            images = search_pexels(query, output_dir, count, api_key=key)
            all_images.extend(images)

    return all_images


def generate_search_queries_for_scenes(scenes: list, style: str = "cinematic") -> list[str]:
    """
    Generate image search queries for each scene based on narration text.
    Uses LLM to create relevant visual search terms.
    """
    try:
        from services.llm_client import get_llm
        llm = get_llm()

        queries = []
        for scene in scenes:
            prompt = f"""Generate a short image search query (3-5 words) for this video scene narration.
The image should be: {style}, dramatic, suitable as video background.
Narration: "{scene.text[:100]}"
Output ONLY the search query, nothing else."""

            result = llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=30,
            )
            queries.append(result.strip().strip('"'))

        return queries

    except Exception as e:
        # Fallback: extract keywords from text
        queries = []
        for scene in scenes:
            words = scene.text.split()[:5]
            queries.append(" ".join(words))
        return queries


def _get_extension(url: str) -> str:
    """Get file extension from URL."""
    path = urllib.parse.urlparse(url).path.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        if ext in path:
            return ext
    return ".jpg"


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python image_search.py <query> [output_dir] [count]")
        sys.exit(1)

    query = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "search_results"
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    results = search_google_images(query, out_dir, count)
    print(f"\nDownloaded {len(results)} images")
    for r in results:
        print(f"  {r}")
