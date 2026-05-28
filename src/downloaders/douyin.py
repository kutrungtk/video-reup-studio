"""
Douyin downloader — direct Web API (not yt-dlp).
Based on jiji262/douyin-downloader flow:
- Firefox cookies
- X-Bogus / A-Bogus signing
- /aweme/v1/web/aweme/detail/
- highest no-watermark play_addr URL
"""
from __future__ import annotations

import os
import re
import time
import random
from http.cookiejar import CookieJar
from typing import Dict, Any, Optional
from urllib.parse import urlencode, urlparse

import requests

from .douyin_lib import XBogus, ABogus, BrowserFingerprintGenerator


UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
]

BASE_URL = "https://www.douyin.com"
DETAIL_PATH = "/aweme/v1/web/aweme/detail/"
USER_POST_PATH = "/aweme/v1/web/aweme/post/"


def download_douyin(url: str, output_dir: str, ffmpeg_location: str | None,
                    today: str, delay: int = 5, max_retries: int = 3) -> dict:
    """Download one Douyin video. Returns {'success', 'file', 'message'}."""
    try:
        aweme_id = extract_aweme_id(url)
        if not aweme_id:
            return {'success': False, 'file': None, 'message': 'Không lấy được aweme_id từ link Douyin'}

        cookies = load_firefox_cookies()
        if not cookies:
            return {'success': False, 'file': None, 'message': 'Không đọc được cookie Firefox'}
        if not cookies.get('s_v_web_id'):
            return {'success': False, 'file': None, 'message': 'Thiếu s_v_web_id — mở douyin.com trong Firefox trước'}

        detail = None
        last_err = None
        for attempt in range(max_retries):
            try:
                detail = fetch_video_detail(aweme_id, cookies)
                if detail:
                    break
            except Exception as e:
                last_err = e
            if attempt < max_retries - 1:
                time.sleep(delay if delay > 0 else 3)

        if not detail:
            msg = f'Douyin API không trả aweme_detail ({last_err})' if last_err else 'Douyin API không trả aweme_detail'
            return {'success': False, 'file': None, 'message': msg}

        media_url = pick_best_video_url(detail)
        if not media_url:
            return {'success': False, 'file': None, 'message': 'Không tìm thấy video URL trong aweme_detail'}

        title = sanitize_filename(detail.get('desc') or detail.get('aweme_id') or aweme_id)[:80]
        out_file = os.path.join(output_dir, f'{today}_{title}.mp4')
        ok = download_file(media_url, out_file, cookies)
        if ok and os.path.isfile(out_file) and os.path.getsize(out_file) > 1024:
            return {'success': True, 'file': out_file, 'message': 'OK'}
        return {'success': False, 'file': None, 'message': 'Tải file Douyin thất bại'}
    except Exception as e:
        return {'success': False, 'file': None, 'message': str(e)[:200]}


def extract_aweme_id(url: str) -> Optional[str]:
    """Extract aweme_id from Douyin video URL; follows short URL redirects if needed."""
    m = re.search(r'/video/(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'(?:aweme_id|modal_id)=(\d+)', url)
    if m:
        return m.group(1)
    # short URL: resolve
    if 'v.douyin.com' in url or 'iesdouyin.com' in url:
        try:
            r = requests.get(url, allow_redirects=True, timeout=15, headers={'User-Agent': random.choice(UA_POOL)})
            return extract_aweme_id(r.url)
        except Exception:
            return None
    return None


def load_firefox_cookies() -> Dict[str, str]:
    """Use yt-dlp's browser cookie loader for Firefox."""
    import yt_dlp
    opts = {'quiet': True, 'cookiesfrombrowser': ('firefox',)}
    with yt_dlp.YoutubeDL(opts) as ydl:
        jar: CookieJar = ydl.cookiejar
        cookies = {}
        for c in jar:
            if 'douyin.com' in c.domain or '.douyin.com' in c.domain:
                cookies[c.name] = c.value
        return cookies


def default_query(cookies: Dict[str, str]) -> Dict[str, Any]:
    return {
        'device_platform': 'webapp',
        'aid': '6383',
        'channel': 'channel_pc_web',
        'update_version_code': '170400',
        'pc_client_type': '1',
        'pc_libra_divert': 'Windows',
        'version_code': '290100',
        'version_name': '29.1.0',
        'cookie_enabled': 'true',
        'screen_width': '1536',
        'screen_height': '864',
        'browser_language': 'zh-CN',
        'browser_platform': 'Win32',
        'browser_name': 'Chrome',
        'browser_version': '139.0.0.0',
        'browser_online': 'true',
        'engine_name': 'Blink',
        'engine_version': '139.0.0.0',
        'os_name': 'Windows',
        'os_version': '10',
        'cpu_core_num': '16',
        'device_memory': '8',
        'platform': 'PC',
        'downlink': '10',
        'effective_type': '4g',
        'round_trip_time': '200',
        'support_h265': '1',
        'support_dash': '1',
        'uifid': '',
        'msToken': cookies.get('msToken', ''),
    }


def sign_url(base_url: str, params: Dict[str, Any], ua: str) -> str:
    query = urlencode(params)
    # Prefer A-Bogus; fallback X-Bogus
    if ABogus and BrowserFingerprintGenerator:
        try:
            fp = BrowserFingerprintGenerator.generate_fingerprint('Chrome')
            signer = ABogus(fp=fp, user_agent=ua)
            params_with_ab, _ab, _ua, _body = signer.generate_abogus(query, '')
            return f'{base_url}?{params_with_ab}'
        except Exception:
            pass
    signed, _xb, _ua = XBogus(ua).build(f'{base_url}?{query}')
    return signed


def fetch_video_detail(aweme_id: str, cookies: Dict[str, str]) -> Optional[Dict[str, Any]]:
    ua = random.choice(UA_POOL)
    params = default_query(cookies)
    params.update({'aweme_id': aweme_id})
    data = request_json(DETAIL_PATH, params, cookies, ua, referer=f'{BASE_URL}/video/{aweme_id}')
    return data.get('aweme_detail') if isinstance(data, dict) else None


def request_json(path: str, params: Dict[str, Any], cookies: Dict[str, str], ua: str,
                 referer: str = BASE_URL) -> Dict[str, Any]:
    url = sign_url(f'{BASE_URL}{path}', params, ua)
    headers = {
        'User-Agent': ua,
        'Referer': referer,
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    r = requests.get(url, headers=headers, cookies=cookies, timeout=30)
    if r.status_code != 200 or not r.content:
        return {}
    data = r.json()
    return data if isinstance(data, dict) else {}


def fetch_user_posts(sec_uid: str, cookies: Dict[str, str], limit: int = 50) -> list[Dict[str, Any]]:
    """Fetch Douyin user post list by sec_uid."""
    items: list[Dict[str, Any]] = []
    max_cursor = 0
    has_more = True
    while has_more and len(items) < limit:
        ua = random.choice(UA_POOL)
        params = default_query(cookies)
        params.update({
            'sec_user_id': sec_uid,
            'max_cursor': max_cursor,
            'count': min(18, max(1, limit - len(items))),
            'show_live_replay_strategy': '1',
            'need_time_list': '1',
            'time_list_query': '0',
            'whale_cut_token': '',
            'cut_version': '1',
            'publish_video_strategy_type': '2',
        })
        data = request_json(USER_POST_PATH, params, cookies, ua, referer=f'{BASE_URL}/user/{sec_uid}')
        aweme_list = data.get('aweme_list') or []
        if not aweme_list:
            break
        items.extend([x for x in aweme_list if isinstance(x, dict)])
        has_more = bool(data.get('has_more'))
        max_cursor = data.get('max_cursor') or data.get('cursor') or 0
        if has_more:
            time.sleep(1)
    return items[:limit]


def scan_author_from_video(url: str, limit: int = 50) -> list[Dict[str, Any]]:
    """Given a Douyin video/modal URL, return author's recent posts as UI-ready dicts."""
    aweme_id = extract_aweme_id(url)
    if not aweme_id:
        raise ValueError('Không lấy được aweme_id từ link Douyin')
    cookies = load_firefox_cookies()
    detail = fetch_video_detail(aweme_id, cookies)
    if not detail:
        raise RuntimeError('Không lấy được aweme_detail')
    author = detail.get('author') or {}
    sec_uid = author.get('sec_uid') or author.get('sec_user_id')
    if not sec_uid:
        raise RuntimeError('Không lấy được sec_uid tác giả')
    posts = fetch_user_posts(sec_uid, cookies, limit=limit)
    if not posts:
        # fallback: current video only
        posts = [detail]
    out = []
    for item in posts:
        aid = str(item.get('aweme_id') or item.get('group_id') or '')
        if not aid:
            continue
        out.append({
            'title': item.get('desc') or aid,
            'url': f'https://www.douyin.com/video/{aid}',
            'duration': int((item.get('duration') or 0) / 1000),
            'views': (item.get('statistics') or {}).get('play_count', 0),
        })
    return out


def pick_best_video_url(aweme: Dict[str, Any]) -> Optional[str]:
    video = aweme.get('video') or {}
    candidates = []
    for br in video.get('bit_rate') or []:
        play = br.get('play_addr') or {}
        bitrate = br.get('bit_rate') or 0
        width = play.get('width') or video.get('width') or 0
        for u in play.get('url_list') or []:
            if u:
                watermark_penalty = 1 if is_watermarked(u) else 0
                candidates.append((watermark_penalty, -int(bitrate), -int(width), u))
    # fallback
    play = video.get('play_addr') or {}
    for u in play.get('url_list') or []:
        candidates.append((1 if is_watermarked(u) else 0, 0, 0, u))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def is_watermarked(url: str) -> bool:
    s = url.lower()
    return 'watermark=1' in s or 'watermark%3d1' in s or 'playwm' in s


def download_file(url: str, out_file: str, cookies: Dict[str, str]) -> bool:
    ua = random.choice(UA_POOL)
    headers = {
        'User-Agent': ua,
        'Referer': BASE_URL,
        'Accept': '*/*',
        'Range': 'bytes=0-',
    }
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    tmp = out_file + '.part'
    with requests.get(url, headers=headers, cookies=cookies, stream=True, timeout=60) as r:
        if r.status_code not in (200, 206):
            return False
        with open(tmp, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 512):
                if chunk:
                    f.write(chunk)
    if os.path.getsize(tmp) <= 1024:
        return False
    if os.path.exists(out_file):
        os.remove(out_file)
    os.replace(tmp, out_file)
    return True


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(name))
    name = re.sub(r'\s+', ' ', name).strip()
    return name or 'douyin_video'
