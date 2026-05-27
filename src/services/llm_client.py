"""
Video Reup Studio Rebuild — LLM Fallback Chain
Auto-retry with model fallback when quota/errors occur.
Learned from NAVTools gemini_with_fallback.py.
"""

import json
import time
from typing import Optional

import requests

from config.settings import get_settings


# Default model chain — try in order, fallback on error
# All models go through 9router (localhost:20128)
DEFAULT_MODEL_CHAIN = [
    "gemini-2.5-flash",       # fast, good quality (via 9router)
    "gemini-2.0-flash",       # fallback (via 9router)
    "gpt-4o-mini",            # another fallback (via 9router)
]

# Errors that should trigger fallback (not retry)
FALLBACK_ERRORS = [
    "PERMISSION_DENIED",
    "quota exceeded",
    "model not found",
    "rate limit",
    "429",
]

# Errors that should trigger retry (transient)
RETRY_ERRORS = [
    "timeout",
    "connection",
    "500",
    "502",
    "503",
    "504",
]


class LLMClient:
    """
    LLM client with fallback chain and retry logic.
    Calls OpenAI-compatible API (9router).
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        model_chain: Optional[list[str]] = None,
        max_retries: int = 3,
        timeout: int = 60,
    ):
        settings = get_settings()
        self._endpoint = (endpoint or settings.get("llm_endpoint")).rstrip("/")
        self._api_key = api_key or settings.get("api_key")
        # Model from settings first, then fallback chain
        user_model = settings.get("llm_model")
        if user_model and user_model != "auto":
            self._model_chain = [user_model] + DEFAULT_MODEL_CHAIN
        else:
            self._model_chain = model_chain or DEFAULT_MODEL_CHAIN
        self._max_retries = max_retries
        self._timeout = timeout
        self._current_model_idx = 0

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        model: Optional[str] = None,
    ) -> str:
        """
        Send chat completion request with fallback chain.
        
        Args:
            messages: List of {role, content} dicts
            temperature: Sampling temperature
            max_tokens: Max response tokens
            model: Override model (skip chain)
        
        Returns:
            Response text content
        """
        models_to_try = [model] if model else self._model_chain[self._current_model_idx:]

        for i, m in enumerate(models_to_try):
            try:
                result = self._call_api(m, messages, temperature, max_tokens)
                return result
            except FallbackError as e:
                print(f"[LLM] Model '{m}' failed (fallback): {e}")
                if i < len(models_to_try) - 1:
                    print(f"[LLM] Trying next model: {models_to_try[i+1]}")
                    continue
                else:
                    raise RuntimeError(f"All models exhausted. Last error: {e}")
            except RetryError as e:
                # Retry same model
                for attempt in range(self._max_retries):
                    wait = (attempt + 1) * 2
                    print(f"[LLM] Retry {attempt+1}/{self._max_retries} in {wait}s: {e}")
                    time.sleep(wait)
                    try:
                        return self._call_api(m, messages, temperature, max_tokens)
                    except (RetryError, FallbackError):
                        continue
                # Retries exhausted, try next model
                if i < len(models_to_try) - 1:
                    continue
                raise RuntimeError(f"All retries exhausted for '{m}': {e}")

        raise RuntimeError("No models available")

    def translate(self, text: str, target_lang: str, source_lang: str = "auto") -> str:
        """Translate text using LLM."""
        messages = [
            {"role": "system", "content": f"Translate the following text to {target_lang}. Output only the translation, nothing else."},
            {"role": "user", "content": text},
        ]
        return self.chat(messages, temperature=0.2)

    def rewrite_subtitle(self, text: str, target_lang: str, style: str = "natural") -> str:
        """Rewrite subtitle text for target language."""
        messages = [
            {"role": "system", "content": (
                f"You are a professional subtitle translator. "
                f"Rewrite the following subtitle text in {target_lang}. "
                f"Keep it concise (subtitles should be short). "
                f"Style: {style}. Output only the translation."
            )},
            {"role": "user", "content": text},
        ]
        return self.chat(messages, temperature=0.3)

    def generate_image_prompt(self, scene_text: str, context: str = "") -> str:
        """Generate AI image prompt from scene description."""
        messages = [
            {"role": "system", "content": (
                "You are a visual director for viral short-form videos. "
                "Generate a detailed, creative image prompt for an AI image generator. "
                "Make it visually stunning, cinematic, eye-catching. "
                "Vertical format (9:16). NO text in the image. "
                "Output ONLY the image prompt (1-3 sentences, under 80 words)."
            )},
            {"role": "user", "content": f"Scene: {scene_text}\nContext: {context[:150]}"},
        ]
        return self.chat(messages, temperature=0.9, max_tokens=150)

    def _call_api(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Make single API call. Raises FallbackError or RetryError."""
        url = f"{self._endpoint}/chat/completions"

        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if model and model != "auto":
            payload["model"] = model

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self._timeout)
        except requests.Timeout:
            raise RetryError("Request timeout")
        except requests.ConnectionError:
            raise RetryError("Connection error")

        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            return content

        # Handle errors
        error_text = resp.text[:300]
        status = resp.status_code

        # Check if fallback or retry
        if any(e in error_text.lower() for e in FALLBACK_ERRORS) or status == 403:
            raise FallbackError(f"HTTP {status}: {error_text}")
        elif status == 429 or any(e in error_text.lower() for e in RETRY_ERRORS):
            raise RetryError(f"HTTP {status}: {error_text}")
        elif status >= 500:
            raise RetryError(f"HTTP {status}: {error_text}")
        else:
            raise FallbackError(f"HTTP {status}: {error_text}")


class FallbackError(Exception):
    """Error that should trigger model fallback."""
    pass


class RetryError(Exception):
    """Error that should trigger retry with same model."""
    pass


# Singleton
_client: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    """Get singleton LLM client."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
