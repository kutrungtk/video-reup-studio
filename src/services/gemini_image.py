"""
Video Reup Studio Rebuild — Gemini Image Service (v4)
Generate images via Google ImageFX using Playwright headless + injected cookies.

Pattern from NAVTools BrowserManager + FlowClient:
- Login: Chrome thật (visible) → user login → export cookies → ĐÓNG Chrome
- Generate: Launch Playwright Chromium HEADLESS + inject cookies → page.evaluate(fetch API)
- Token refresh: page.evaluate(fetch('/fx/api/auth/session')) từ trong browser
- On 401/403 → renew_token() → retry

Fallback chain:
1. Playwright headless + cookies (like NAVTools) — free, best
2. 9router/local endpoint — needs 9router running
3. Direct API key — limited
"""

import os
import json
import base64
import time
import asyncio
from typing import Optional

import requests


# Constants from NAVTools
AISANDBOX_BASE = "https://aisandbox-pa.googleapis.com/v1"
SESSION_URL = "https://labs.google/fx/api/auth/session"
FLOW_URL = "https://labs.google/fx/tools/image-fx"
MAX_RETRY = 3


class GeminiImageService:
    """
    Generate images using Google ImageFX.
    Uses Playwright headless + injected cookies (like NAVTools).
    """

    def __init__(self, api_key: str = "", session_token: str = ""):
        self._api_key = api_key
        self._session_token = session_token

    @classmethod
    def from_settings(cls) -> "GeminiImageService":
        """Create from app settings."""
        from config.settings import get_settings
        s = get_settings()
        return cls(
            api_key=s.get("gemini_api_key") or "",
            session_token=s.get("gemini_session_token") or "",
        )

    # === Public API ===

    def generate_image(
        self,
        prompt: str,
        output_path: str,
        width: int = 1080,
        height: int = 1920,
        model: str = "imagen-3.0-generate-002",
    ) -> Optional[str]:
        """Generate image — tries headless browser, then 9router, then API key."""
        # Try headless browser + cookies (like NAVTools)
        cookies = self._load_cookies()
        if cookies:
            result = self._generate_via_headless_browser(prompt, output_path, width, height, cookies)
            if result:
                return result

        # Try 9router/local
        result = self._generate_via_local(prompt, output_path, width, height)
        if result:
            return result

        # Try API key
        if self._api_key:
            result = self._generate_via_api(prompt, output_path, width, height, model)
            if result:
                return result

        print(f"[Gemini] All image generation methods failed")
        return None

    # === Headless Browser Mode (like NAVTools) ===

    def _generate_via_headless_browser(self, prompt: str, output_path: str, w: int, h: int,
                                        cookies: list[dict]) -> Optional[str]:
        """Launch Chrome thật headless via CDP, inject cookies, call API via page.evaluate."""
        try:
            result = asyncio.run(self._async_generate(prompt, output_path, w, h, cookies))
            return result
        except RuntimeError as e:
            # If event loop already running, use thread
            if "cannot be called from a running event loop" in str(e):
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self._async_generate(prompt, output_path, w, h, cookies))
                    return future.result(timeout=120)
            print(f"[Gemini] Headless browser error: {e}")
            return None
        except Exception as e:
            print(f"[Gemini] Headless browser error: {e}")
            return None

    async def _async_generate(self, prompt: str, output_path: str, w: int, h: int,
                               cookies: list[dict]) -> Optional[str]:
        """Async: Use system Chrome (headless=False, hidden) + injected cookies.
        NAVTools pattern: real Chrome binary, NOT headless, window hidden off-screen.
        """
        from playwright.async_api import async_playwright
        import shutil

        aspect_ratio = "9:16" if h > w else ("16:9" if w > h else "1:1")

        # Filter cookies for Playwright compatibility
        valid_cookies = self._filter_cookies_for_playwright(cookies)
        if not valid_cookies:
            print("[Gemini] No valid cookies for Playwright")
            return None

        # Find system Chrome (NAVTools uses real Chrome, NOT bundled Chromium)
        chrome_path = self._find_chrome()

        async with async_playwright() as p:
            # Launch like NAVTools: headless=False, system Chrome, window hidden
            launch_args = [
                "--window-position=-10000,-10000",
                "--window-size=1,1",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-default-apps",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-extensions",
                "--disable-features=TranslateUI,GlobalMediaControls",
            ]

            browser = await p.chromium.launch(
                headless=False,  # NAVTools uses headless=False!
                executable_path=chrome_path,  # System Chrome
                args=launch_args,
            )

            context = await browser.new_context()

            # Anti-detection scripts (like NAVTools)
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
            """)

            # Inject cookies
            try:
                await context.add_cookies(valid_cookies)
                print(f"[Gemini] Injected {len(valid_cookies)} cookies")
            except Exception as e:
                print(f"[Gemini] Cookie injection error: {e}")
                await browser.close()
                return None

            page = await context.new_page()

            # Navigate to labs.google/fx (like NAVTools ensure_token)
            print("[Gemini] Navigating to labs.google/fx...")
            await page.goto("https://labs.google/fx", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # Check if sign-in needed
            try:
                sign_in = await page.query_selector(
                    'a[href*="accounts.google.com"], button:has-text("Sign in"), a:has-text("Sign in")'
                )
                if sign_in and await sign_in.is_visible():
                    print("[Gemini] Clicking Sign in...")
                    await sign_in.click()
                    await asyncio.sleep(5)
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                else:
                    print("[Gemini] Already signed in")
            except Exception:
                pass

            # Navigate to image-fx page (loads reCAPTCHA script)
            print("[Gemini] Navigating to image-fx page...")
            await page.goto("https://labs.google/fx/tools/image-fx", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(5)

            # Get token (like NAVTools ensure_token)
            token = await self._get_token_from_page(page)
            if not token:
                print("[Gemini] Trying video-fx for token...")
                await page.goto("https://labs.google/fx/tools/video-fx", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
                token = await self._get_token_from_page(page)

            if not token:
                print("[Gemini] Could not get token")
                await browser.close()
                return None

            self._session_token = token
            from config.settings import get_settings
            get_settings().set("gemini_session_token", token)

            # Harvest reCAPTCHA (like NAVTools recaptcha_provider)
            print("[Gemini] Harvesting reCAPTCHA token...")
            recaptcha_result = await page.evaluate("""async (action) => {
                // Wait for grecaptcha to load
                for (let i = 0; i < 30; i++) {
                    if (typeof grecaptcha !== 'undefined' && (grecaptcha.enterprise || grecaptcha.execute)) break;
                    await new Promise(r => setTimeout(r, 500));
                }

                // Find site key from script tags
                let siteKey = null;
                const scripts = document.querySelectorAll('script[src*="recaptcha"]');
                for (const s of scripts) {
                    const m = s.src.match(/[?&]render=([^&]+)/);
                    if (m) { siteKey = m[1]; break; }
                }

                if (typeof grecaptcha !== 'undefined' && grecaptcha.enterprise) {
                    try {
                        const token = await grecaptcha.enterprise.execute(siteKey, {action: action});
                        if (token) return {token, key: siteKey};
                    } catch(e) {
                        return {error: e.message, key: siteKey};
                    }
                }
                return {error: 'grecaptcha_not_available', key: siteKey};
            }""", "image_generate")

            recaptcha_token = ""
            if isinstance(recaptcha_result, dict) and recaptcha_result.get("token"):
                recaptcha_token = recaptcha_result["token"]
                print(f"[Gemini] ✅ reCAPTCHA: {recaptcha_token[:20]}...")
            else:
                print(f"[Gemini] ⚠ reCAPTCHA failed: {recaptcha_result}")
                # Continue anyway — some requests work without it

            # Build payload (whisk-proxy format + NAVTools recaptchaToken in clientContext)
            import uuid as _uuid
            aspect_enum_map = {
                "9:16": "IMAGE_ASPECT_RATIO_PORTRAIT",
                "16:9": "IMAGE_ASPECT_RATIO_LANDSCAPE",
                "1:1": "IMAGE_ASPECT_RATIO_SQUARE",
            }
            payload = {
                "userInput": {
                    "candidatesCount": 1,
                    "prompts": [prompt],
                    "seed": int(time.time()) % 2147483647,
                },
                "clientContext": {
                    "sessionId": ";" + str(int(time.time() * 1000)),
                    "tool": "IMAGE_FX",
                    "recaptchaToken": recaptcha_token,
                },
                "aspectRatio": aspect_enum_map.get(aspect_ratio, "IMAGE_ASPECT_RATIO_PORTRAIT"),
                "modelInput": {
                    "modelNameType": "IMAGEN_3_5",
                },
            }

            # Call API from inside browser
            # URL: v1:runImageFx (NO slash before colon — confirmed by whisk-proxy)
            result = await self._browser_sandbox_request(page, ":runImageFx", payload)

            if result:
                self._last_media_name = None
                img_b64 = self._extract_image_from_response(result)
                if img_b64:
                    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(img_b64))
                    print(f"[Gemini] ✅ Image generated: {output_path}")
                    await browser.close()
                    return output_path
                elif self._last_media_name:
                    # Image returned as fife URL — download via browser
                    print(f"[Gemini] Downloading via fife: {self._last_media_name[:50]}...")
                    img_data = await page.evaluate("""async (name) => {
                        try {
                            const url = `https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?input=${encodeURIComponent(JSON.stringify({json:{name}}))}`;
                            const r = await fetch(url, {credentials: "include"});
                            if (r.redirected) {
                                const imgR = await fetch(r.url);
                                const buf = await imgR.arrayBuffer();
                                return {b64: btoa(String.fromCharCode(...new Uint8Array(buf)))};
                            }
                            const data = await r.json();
                            const redirect = data?.result?.data?.json?.url || data?.result?.data?.json?.redirectUrl;
                            if (redirect) {
                                const imgR = await fetch(redirect);
                                const buf = await imgR.arrayBuffer();
                                return {b64: btoa(String.fromCharCode(...new Uint8Array(buf)))};
                            }
                            return {error: "no redirect url", keys: Object.keys(data || {})};
                        } catch(e) { return {error: e.message}; }
                    }""", self._last_media_name)

                    if isinstance(img_data, dict) and img_data.get("b64"):
                        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(base64.b64decode(img_data["b64"]))
                        print(f"[Gemini] ✅ Image downloaded: {output_path}")
                        await browser.close()
                        return output_path
                    else:
                        print(f"[Gemini] Download failed: {img_data}")
                else:
                    print(f"[Gemini] No image in response: {json.dumps(result)[:300]}")

            await browser.close()
            
        return None

    def _find_chrome(self) -> Optional[str]:
        """Find system Chrome executable."""
        import shutil
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

    def _filter_cookies_for_playwright(self, cookies: list[dict]) -> list[dict]:
        """Filter and fix cookies for Playwright add_cookies.
        Use 'url' for ALL cookies (safest approach — avoids domain format issues).
        """
        valid = []
        for c in cookies:
            if not c.get("name") or not c.get("value"):
                continue
            domain = c.get("domain", "")
            if not domain:
                continue

            # Build URL from domain (works for all cookie types)
            scheme = "https" if c.get("secure") else "http"
            clean_domain = domain.lstrip(".")
            url = f"{scheme}://{clean_domain}/"

            cookie = {
                "name": c["name"],
                "value": c["value"],
                "url": url,
            }

            # sameSite
            same_site = c.get("sameSite", "")
            if same_site and same_site in ("Strict", "Lax", "None"):
                cookie["sameSite"] = same_site
            else:
                cookie["sameSite"] = "Lax"

            if c.get("secure"):
                cookie["secure"] = True
            if c.get("httpOnly"):
                cookie["httpOnly"] = True

            # expires: negative → omit (session cookie)
            expires = c.get("expires")
            if expires and isinstance(expires, (int, float)) and expires > 0:
                cookie["expires"] = float(expires)

            valid.append(cookie)
        return valid

    async def _browser_sandbox_request(self, page, endpoint: str, payload: dict) -> Optional[dict]:
        """Call API from inside browser (like NAVTools _browser_sandbox_request).
        On 401/403 → renew token → retry.
        """
        # Build URL: endpoints starting with ":" go directly after base (no slash)
        # e.g. ":runImageFx" → "https://aisandbox-pa.googleapis.com/v1:runImageFx"
        if endpoint.startswith(":"):
            url = f"{AISANDBOX_BASE}{endpoint}"
        else:
            url = f"{AISANDBOX_BASE}/{endpoint.lstrip('/')}"
        body_json = json.dumps(payload)
        print(f"[Gemini] API URL: {url}")
        print(f"[Gemini] Payload keys: {list(payload.keys())}")

        for attempt in range(MAX_RETRY):
            result = await page.evaluate(
                """async ({url, token, body}) => {
                    const r = await fetch(url, {
                        method: "POST",
                        headers: {"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                        body
                    });
                    const text = await r.text();
                    try { return {status: r.status, ok: r.ok, json: JSON.parse(text)}; }
                    catch(e) { return {status: r.status, ok: r.ok, text}; }
                }""",
                {"url": url, "token": self._session_token, "body": body_json},
            )

            if result.get("ok"):
                return result.get("json")

            status = result.get("status")
            if status in (401, 403):
                print(f"[Gemini] HTTP {status}, renewing token (attempt {attempt+1}/{MAX_RETRY})...")
                new_token = await self._get_token_from_page(page)
                if new_token:
                    self._session_token = new_token
                    from config.settings import get_settings
                    get_settings().set("gemini_session_token", new_token)
                await asyncio.sleep(1 + attempt)
            else:
                error_text = result.get("text", "") or json.dumps(result.get("json", {}))
                print(f"[Gemini] API error HTTP {status}: {error_text[:500]}")
                return None

        print(f"[Gemini] Failed after {MAX_RETRY} retries")
        return None

    async def _get_token_from_page(self, page) -> Optional[str]:
        """Get access token from page (like NAVTools ensure_token)."""
        try:
            result = await page.evaluate(
                """async (url) => {
                    const r = await fetch(url, {credentials: "include"});
                    if (!r.ok) return {error: r.status};
                    return await r.json();
                }""",
                SESSION_URL,
            )
            token = (result or {}).get("accessToken") or (result or {}).get("access_token")
            if token and len(token) > 10:
                print(f"[Gemini] ✅ Token: {token[:25]}...")
                return token
            else:
                print(f"[Gemini] Token fetch result: {result}")
        except Exception as e:
            print(f"[Gemini] Token fetch error: {e}")
        return None

    # === Fallback: _generate_via_session (requests, less reliable) ===

    def _generate_via_session(self, prompt: str, output_path: str, w: int, h: int,
                              aspect_ratio: str = "", count: int = 1, ref_image: str = "") -> Optional[str]:
        """Fallback: call API with token + cookies via requests."""
        if not self._session_token:
            return None

        cookie_str = self._get_cookie_string()
        headers = {
            "Authorization": f"Bearer {self._session_token}",
            "Content-Type": "application/json",
            "Origin": "https://labs.google",
            "Referer": "https://labs.google/fx/tools/image-fx",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
        }
        if cookie_str:
            headers["Cookie"] = cookie_str

        if not aspect_ratio:
            aspect_ratio = "9:16" if h > w else ("16:9" if w > h else "1:1")

        payload = {
            "userInput": {
                "candidatesCount": min(count, 4),
                "prompts": [{"text": prompt}],
            },
            "clientContext": {"tool": "IMAGE_FX"},
            "aspectRatio": aspect_ratio,
        }

        try:
            resp = requests.post(f"{AISANDBOX_BASE}/:runImageFx", json=payload, headers=headers, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                img_b64 = self._extract_image_from_response(data)
                if img_b64:
                    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(base64.b64decode(img_b64))
                    print(f"[Gemini] Session+cookies OK: {output_path}")
                    return output_path
            elif resp.status_code in (401, 403):
                print(f"[Gemini] Session+cookies failed (HTTP {resp.status_code})")
            else:
                print(f"[Gemini] Session error {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[Gemini] Session request failed: {e}")

        return None

    # === 9router/Local Mode ===

    def _generate_via_local(self, prompt: str, output_path: str, w: int, h: int) -> Optional[str]:
        """Generate via local 9router endpoint (OpenAI-compatible images API)."""
        try:
            from config.settings import get_settings
            settings = get_settings()
            endpoint = settings.get("image_endpoint") or settings.get("llm_endpoint") or ""
            api_key = settings.get("image_api_key") or settings.get("api_key") or ""
            model = settings.get("image_model") or "cx/gpt-5.5-image"

            if not endpoint:
                return None

            url = f"{endpoint.rstrip('/')}/images/generations"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            if w == h:
                size_str = "1024x1024"
            elif w > h:
                size_str = "1792x1024"
            else:
                size_str = "1024x1792"

            payload = {
                "model": model,
                "prompt": prompt,
                "n": 1,
                "size": size_str,
                "quality": "auto",
                "background": "auto",
                "image_detail": "high",
                "output_format": "png",
            }

            resp = requests.post(url, json=payload, headers=headers, timeout=120)

            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and data["data"]:
                    img_info = data["data"][0]
                    if "b64_json" in img_info:
                        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(base64.b64decode(img_info["b64_json"]))
                        print(f"[Image] 9router OK: {output_path}")
                        return output_path
                    elif "url" in img_info:
                        img_resp = requests.get(img_info["url"], timeout=30)
                        if img_resp.status_code == 200:
                            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                            with open(output_path, "wb") as f:
                                f.write(img_resp.content)
                            print(f"[Image] 9router URL OK: {output_path}")
                            return output_path
            else:
                print(f"[Image] 9router error {resp.status_code}: {resp.text[:200]}")

        except Exception as e:
            print(f"[Image] 9router failed: {e}")

        return None

    # === API Key Mode ===

    def _generate_via_api(self, prompt: str, output_path: str, w: int, h: int, model: str) -> Optional[str]:
        """Generate via Gemini API key (official, limited free tier)."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateImages"
            headers = {"Content-Type": "application/json"}
            params = {"key": self._api_key}

            payload = {
                "prompt": prompt,
                "config": {
                    "numberOfImages": 1,
                    "aspectRatio": self._get_aspect_ratio(w, h),
                },
            }

            resp = requests.post(url, json=payload, headers=headers, params=params, timeout=60)

            if resp.status_code == 200:
                data = resp.json()
                images = data.get("generatedImages", [])
                if images:
                    img_b64 = images[0].get("image", {}).get("imageBytes", "")
                    if img_b64:
                        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(base64.b64decode(img_b64))
                        print(f"[Gemini] API mode OK: {output_path}")
                        return output_path
            else:
                print(f"[Gemini] API error {resp.status_code}: {resp.text[:200]}")

        except Exception as e:
            print(f"[Gemini] API mode failed: {e}")

        return None

    # === Helpers ===

    def _load_cookies(self) -> list[dict]:
        """Load cookies from file for Playwright injection."""
        try:
            from config.settings import get_settings
            cookies_path = get_settings().get("gemini_cookies_path") or ""
            if not cookies_path or not os.path.isfile(cookies_path):
                from config.constants import PROJECT_ROOT
                cookies_path = os.path.join(PROJECT_ROOT, ".browser_profile", "cookies_export.json")
            if not os.path.isfile(cookies_path):
                return []

            with open(cookies_path, "r", encoding="utf-8") as f:
                cookies_list = json.load(f)

            # Filter and format for Playwright add_cookies
            valid = []
            for c in cookies_list:
                if not c.get("name") or not c.get("value"):
                    continue
                cookie = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ""),
                    "path": c.get("path", "/"),
                }
                # Playwright needs either url or domain
                if cookie["domain"]:
                    # Ensure domain starts with . for proper matching
                    if not cookie["domain"].startswith("."):
                        cookie["domain"] = "." + cookie["domain"]
                else:
                    continue
                if c.get("secure"):
                    cookie["secure"] = True
                if c.get("httpOnly"):
                    cookie["httpOnly"] = True
                if c.get("sameSite"):
                    ss = c["sameSite"].capitalize()
                    if ss in ("Strict", "Lax", "None"):
                        cookie["sameSite"] = ss
                valid.append(cookie)

            return valid

        except Exception as e:
            print(f"[Gemini] Failed to load cookies: {e}")
            return []

    def _get_cookie_string(self) -> str:
        """Load cookies as header string (for requests fallback)."""
        try:
            from config.settings import get_settings
            cookies_path = get_settings().get("gemini_cookies_path") or ""
            if not cookies_path or not os.path.isfile(cookies_path):
                from config.constants import PROJECT_ROOT
                cookies_path = os.path.join(PROJECT_ROOT, ".browser_profile", "cookies_export.json")
            if not os.path.isfile(cookies_path):
                return ""

            with open(cookies_path, "r", encoding="utf-8") as f:
                cookies_list = json.load(f)

            parts = []
            for c in cookies_list:
                domain = c.get("domain", "")
                if "google" in domain or "labs.google" in domain:
                    parts.append(f"{c['name']}={c['value']}")
            return "; ".join(parts)

        except Exception:
            return ""

    def _extract_image_from_response(self, data: dict) -> Optional[str]:
        """Extract base64 image OR download URL from various response shapes (like NAVTools)."""
        if not isinstance(data, dict):
            return None

        # Shape 1: imagePanels[0].generatedImages[0].encodedImage
        panels = data.get("imagePanels", [])
        if panels:
            images = panels[0].get("generatedImages", [])
            if images:
                enc = images[0].get("encodedImage")
                if enc:
                    return enc

        # Shape 2: media[0].image.generatedImage (NAVTools shape — may have fife URL)
        media = data.get("media", [])
        if isinstance(media, list) and media:
            first = media[0]
            if isinstance(first, dict):
                img_wrap = first.get("image") or {}
                gen = img_wrap.get("generatedImage") or {}
                if gen.get("encodedImage"):
                    return gen["encodedImage"]
                # Check for fife URL (download link)
                name = gen.get("name") or first.get("name") or ""
                if name:
                    # Store name for URL download
                    self._last_media_name = name

        # Shape 3: generatedImages[0].encodedImage
        gen = data.get("generatedImages", [])
        if isinstance(gen, list) and gen:
            enc = gen[0].get("encodedImage")
            if enc:
                return enc
            # Check for fife/name
            name = gen[0].get("name") or ""
            if name:
                self._last_media_name = name

        # Shape 4: responses[0]...
        responses = data.get("responses", [])
        if isinstance(responses, list):
            for resp_item in responses:
                result = self._extract_image_from_response(resp_item)
                if result:
                    return result

        return None

    @staticmethod
    def _get_aspect_ratio(w: int, h: int) -> str:
        if w > h:
            return "LANDSCAPE_16_9"
        elif h > w:
            return "PORTRAIT_9_16"
        return "SQUARE_1_1"

    @staticmethod
    def _encode_image_base64(image_path: str, max_size: int = 1536) -> Optional[str]:
        """Encode image to base64, resize if too large."""
        try:
            from PIL import Image
            import io

            img = Image.open(image_path)
            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")

        except Exception as e:
            print(f"[Image] Failed to encode reference: {e}")
            return None


# === Singleton ===

_instance: Optional[GeminiImageService] = None


def get_gemini_image_service() -> GeminiImageService:
    """Get singleton Gemini image service."""
    global _instance
    if _instance is None:
        _instance = GeminiImageService.from_settings()
    return _instance


def reset_gemini_image_service():
    """Reset singleton (after settings change or re-login)."""
    global _instance
    _instance = None
