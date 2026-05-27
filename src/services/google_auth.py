"""
Video Reup Studio Rebuild — Google Auth Service (v2)
Dùng Chrome THẬT (không phải Playwright Chromium) để tránh bị Google chặn.

Cơ chế (giống NAVTools):
1. Mở Chrome thật với --remote-debugging-port + profile riêng
2. User login Google bình thường
3. Playwright CONNECT vào Chrome qua CDP (không launch mới)
4. Export cookies + lấy session token
5. Đóng Chrome

Tại sao Chrome thật? Vì Google detect Playwright Chromium là automation → chặn login.
Chrome thật + profile riêng = Google không detect.
"""

import asyncio
import json
import os
import subprocess
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import get_settings
from config.constants import PROJECT_ROOT


# Dirs
BROWSER_PROFILE_DIR = os.path.join(PROJECT_ROOT, ".browser_profile")
COOKIES_FILE = os.path.join(BROWSER_PROFILE_DIR, "cookies_export.json")
CDP_PORT = 9333  # Remote debugging port


def find_chrome() -> Optional[str]:
    """Find Chrome/Chromium executable on Windows."""
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def login_google_get_session(headless: bool = False) -> Optional[str]:
    """
    Mở Chrome thật → user login → export cookies → lấy token.
    
    Returns:
        Session token hoặc "cookies_saved" hoặc None
    """
    chrome = find_chrome()
    if not chrome:
        print("[Auth] ❌ Chrome not found! Install Google Chrome.")
        return None

    try:
        return asyncio.run(_login_with_real_chrome(chrome))
    except Exception as e:
        print(f"[Auth] Error: {e}")
        return None


async def _login_with_real_chrome(chrome_path: str) -> Optional[str]:
    """Launch real Chrome with CDP, connect Playwright, export cookies."""
    from playwright.async_api import async_playwright

    os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
    profile_dir = os.path.join(BROWSER_PROFILE_DIR, f"chrome_{int(time.time())}")

    # Kill any existing Chrome on our CDP port
    _kill_port(CDP_PORT)

    # Launch Chrome thật with remote debugging
    print(f"[Auth] Launching Chrome: {chrome_path}")
    print(f"[Auth] Profile: {profile_dir}")

    chrome_args = [
        chrome_path,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "https://labs.google/fx",
    ]

    # Start Chrome process
    proc = subprocess.Popen(
        chrome_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print("[Auth] ⚠ Chrome đã mở — hãy đăng nhập Google!")
    print("[Auth] Sau khi login xong, tool sẽ tự động lấy cookies.")
    print("[Auth] Timeout: 5 phút")

    # Wait for Chrome to start
    await asyncio.sleep(3)

    token = None

    try:
        async with async_playwright() as p:
            # Connect to running Chrome via CDP
            print(f"[Auth] Connecting to Chrome (port {CDP_PORT})...")
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")

            # Get the page
            contexts = browser.contexts
            if not contexts:
                print("[Auth] No browser context found")
                return None

            context = contexts[0]
            pages = context.pages
            if not pages:
                page = await context.new_page()
            else:
                page = pages[0]

            # Wait for user to login (check every 3s for 5 minutes)
            print("[Auth] Waiting for login...")
            logged_in = False
            for _ in range(100):  # 100 * 3s = 5 minutes
                await asyncio.sleep(3)
                try:
                    url = page.url
                    # Method 1: URL has /tools/ = definitely in app
                    if "labs.google" in url and "/tools/" in url:
                        logged_in = True
                        break
                    # Method 2: Check for avatar/profile icon on page (user signed in)
                    avatar = await page.query_selector(
                        'img[data-profileimageid], [aria-label*="Account"], [aria-label*="Tài khoản"], '
                        'button[aria-label*="Google"], img[alt*="Avatar"], .gb_A, .gb_d'
                    )
                    if avatar:
                        logged_in = True
                        break
                    # Method 3: No sign-in button visible = already logged in
                    if "labs.google" in url:
                        sign_in = await page.query_selector(
                            'a:has-text("Sign in"), a:has-text("Đăng nhập"), button:has-text("Sign in")'
                        )
                        if not sign_in or not await sign_in.is_visible():
                            # Double check we're on labs.google (not redirected to accounts)
                            if "accounts.google.com" not in url:
                                logged_in = True
                                break
                except Exception:
                    pass

            if not logged_in:
                print("[Auth] ❌ Login timeout (5 min)")
                return None

            print("[Auth] ✅ Login detected!")

            # Navigate to ImageFX to get session
            print("[Auth] Getting session token...")
            await page.goto("https://labs.google/fx/tools/image-fx", wait_until="networkidle")
            await asyncio.sleep(3)

            # Check if we need to sign in on labs.google (separate from Google account login)
            try:
                sign_in_btn = await page.query_selector(
                    'a[href*="accounts.google.com"], button:has-text("Sign in"), a:has-text("Sign in")'
                )
                if sign_in_btn and await sign_in_btn.is_visible():
                    print("[Auth] Clicking Sign in on labs.google...")
                    await sign_in_btn.click()
                    await asyncio.sleep(5)
                    # May open popup or redirect — wait for it
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await asyncio.sleep(3)
            except Exception as e:
                print(f"[Auth] Sign-in check: {e}")

            # Wait for page to be fully ready (labs.google needs time to establish session)
            print("[Auth] Waiting for session to establish...")
            await asyncio.sleep(3)

            # Reload to ensure session is fresh
            await page.reload(wait_until="networkidle")
            await asyncio.sleep(3)

            # Export cookies
            cookies = await context.cookies()
            cookies_data = [
                {k: v for k, v in c.items() if k in ("name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite")}
                for c in cookies
            ]
            with open(COOKIES_FILE, "w", encoding="utf-8") as f:
                json.dump(cookies_data, f)
            print(f"[Auth] Exported {len(cookies_data)} cookies")

            # Get access token — MUST use page.evaluate (fetch from inside browser)
            # This is how NAVTools does it — browser context has the session cookies
            try:
                result = await page.evaluate("""async (url) => {
                    try {
                        const r = await fetch(url, {credentials: "include"});
                        if (!r.ok) return {error: r.status, text: await r.text()};
                        return await r.json();
                    } catch(e) {
                        return {error: e.message};
                    }
                }""", "https://labs.google/fx/api/auth/session")

                token = None
                if isinstance(result, dict):
                    token = result.get("accessToken") or result.get("access_token")

            except Exception as e:
                print(f"[Auth] evaluate failed: {e}")
                token = None
                result = {"error": str(e)}

            if token and len(token) > 10:
                print(f"[Auth] ✅ Token: {token[:25]}...")
                settings = get_settings()
                settings.set("gemini_session_token", token)
                settings.set("gemini_cookies_path", COOKIES_FILE)
            else:
                # Token not found — try alternative: check if page has __NEXT_DATA__
                print(f"[Auth] ⚠ Direct fetch failed: {result}")
                print("[Auth] Trying alternative token extraction...")
                try:
                    # Some Google pages embed token in page data
                    alt_token = await page.evaluate("""() => {
                        // Try window.__NEXT_DATA__
                        if (window.__NEXT_DATA__) {
                            const session = window.__NEXT_DATA__?.props?.pageProps?.session;
                            if (session && session.accessToken) return session.accessToken;
                        }
                        // Try cookies directly
                        const cookies = document.cookie.split(';');
                        for (const c of cookies) {
                            const [name, val] = c.trim().split('=');
                            if (name === '__Secure-next-auth.session-token' || name === 'next-auth.session-token') {
                                return val;
                            }
                        }
                        return null;
                    }""")
                    if alt_token and len(alt_token) > 10:
                        print(f"[Auth] ✅ Alt token: {alt_token[:25]}...")
                        token = alt_token
                        settings = get_settings()
                        settings.set("gemini_session_token", token)
                        settings.set("gemini_cookies_path", COOKIES_FILE)
                    else:
                        print("[Auth] ⚠ No token found, but cookies saved")
                        token = "cookies_saved"
                        get_settings().set("gemini_cookies_path", COOKIES_FILE)
                except Exception as e2:
                    print(f"[Auth] Alt extraction failed: {e2}")
                    token = "cookies_saved"
                    get_settings().set("gemini_cookies_path", COOKIES_FILE)

            # Disconnect — close browser (cookies saved, headless will use them later)
            await browser.close()

    except Exception as e:
        print(f"[Auth] Error during login: {e}")
    finally:
        # Kill Chrome process
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    return token


def _kill_port(port: int):
    """Kill process on given port (Windows)."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid],
                             capture_output=True, timeout=5)
    except Exception:
        pass


def get_cookies() -> list[dict]:
    """Load saved cookies."""
    if os.path.isfile(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def has_valid_session() -> bool:
    """Check if we have saved cookies/token."""
    settings = get_settings()
    token = settings.get("gemini_session_token")
    if token:
        return True
    return os.path.isfile(COOKIES_FILE)


def check_session_valid() -> bool:
    """Check if saved session is still valid."""
    settings = get_settings()
    token = settings.get("gemini_session_token")

    if not token or token == "cookies_saved":
        return os.path.isfile(COOKIES_FILE)

    try:
        import requests
        headers = {
            "Authorization": f"Bearer {token}",
            "Origin": "https://labs.google",
        }
        resp = requests.get(
            "https://aisandbox-pa.googleapis.com/v1/flow/listProjects",
            headers=headers, timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


def get_session_token() -> str:
    """Get saved session token."""
    return get_settings().get("gemini_session_token") or ""


def login_google_simple():
    """Fallback: open browser manually."""
    import webbrowser
    webbrowser.open("https://labs.google/fx/tools/image-fx")
    print("[Auth] Browser opened manually.")
    print("  1. Login Google")
    print("  2. Go to: https://labs.google/fx/api/auth/session")
    print("  3. Copy accessToken → paste in Settings")


if __name__ == "__main__":
    token = login_google_get_session()
    if token:
        print(f"\n✅ Done: {token[:30]}...")
    else:
        print("\n❌ Failed")
