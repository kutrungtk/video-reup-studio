"""
Video Reup Studio - Translator Module
Multi-language translation preserving timestamps.
Supports: EN, VI, ZH, IT, KO, JA — any direction.
"""

import json
import os
import re
from typing import Optional
from dataclasses import dataclass


# Language code mapping
SUPPORTED_LANGUAGES = {
    "en": "english",
    "vi": "vietnamese",
    "zh": "chinese (simplified)",
    "it": "italian",
    "ko": "korean",
    "ja": "japanese",
    "zh-cn": "chinese (simplified)",
    "zh-tw": "chinese (traditional)",
}

# deep-translator language codes
DEEP_TRANSLATOR_CODES = {
    "en": "en",
    "vi": "vi",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-tw": "zh-TW",
    "it": "it",
    "ko": "ko",
    "ja": "ja",
}


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    Translate a single text string.
    
    Args:
        text: Text to translate
        source_lang: Source language code (en, vi, zh, it, ko, ja)
        target_lang: Target language code
    """
    from deep_translator import GoogleTranslator

    src = DEEP_TRANSLATOR_CODES.get(source_lang, source_lang)
    tgt = DEEP_TRANSLATOR_CODES.get(target_lang, target_lang)

    if src == tgt:
        return text

    # Google Translate has a 5000 char limit per request
    if len(text) <= 4500:
        translator = GoogleTranslator(source=src, target=tgt)
        return translator.translate(text)
    else:
        # Split into chunks at sentence boundaries
        return _translate_long_text(text, src, tgt)


def _translate_long_text(text: str, src: str, tgt: str, max_chunk: int = 4500) -> str:
    """Translate long text by splitting at sentence boundaries."""
    from deep_translator import GoogleTranslator

    # Split by sentences
    sentences = re.split(r'(?<=[.!?。！？])\s+', text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_chunk:
            current_chunk += (" " if current_chunk else "") + sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    # Translate each chunk
    translator = GoogleTranslator(source=src, target=tgt)
    translated_chunks = []
    for chunk in chunks:
        translated = translator.translate(chunk)
        translated_chunks.append(translated)

    return " ".join(translated_chunks)


def translate_transcript(
    transcript_data: dict,
    target_lang: str,
    source_lang: Optional[str] = None,
) -> dict:
    """
    Translate entire transcript, preserving timestamps.
    
    Args:
        transcript_data: Transcript dict (from transcriber.py output)
        target_lang: Target language code
        source_lang: Source language (None = use transcript's detected language)
    
    Returns:
        New transcript dict with translated text, same timestamps
    """
    src = source_lang or transcript_data.get("language", "en")
    src = _normalize_lang_code(src)
    tgt = _normalize_lang_code(target_lang)

    if src == tgt:
        print(f"[Translator] Source and target are the same ({src}), skipping.")
        return transcript_data

    print(f"[Translator] Translating {src} → {tgt}...")

    # Collect all segment texts for batch translation
    segments = transcript_data["segments"]
    texts = [seg["text"] for seg in segments]

    # Batch translate (more efficient than one-by-one)
    translated_texts = _batch_translate(texts, src, tgt)

    # Build new transcript with translated text, keeping timestamps
    new_segments = []
    for i, seg in enumerate(segments):
        new_seg = {
            "id": seg["id"],
            "text": translated_texts[i],
            "start": seg["start"],
            "end": seg["end"],
            "words": _estimate_word_timing(translated_texts[i], seg["start"], seg["end"]),
        }
        new_segments.append(new_seg)

    result = {
        "language": tgt,
        "duration": transcript_data["duration"],
        "source": transcript_data.get("source", "unknown"),
        "source_language": src,
        "segments": new_segments,
    }

    print(f"[Translator] Done: {len(new_segments)} segments translated to {tgt}")
    return result


def _batch_translate(texts: list[str], src: str, tgt: str, batch_size: int = 20) -> list[str]:
    """
    Batch translate texts efficiently.
    Uses separator trick to reduce API calls.
    """
    from deep_translator import GoogleTranslator

    src_code = DEEP_TRANSLATOR_CODES.get(src, src)
    tgt_code = DEEP_TRANSLATOR_CODES.get(tgt, tgt)
    translator = GoogleTranslator(source=src_code, target=tgt_code)

    results = []
    separator = " ||| "

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        # Join with separator for batch translation
        combined = separator.join(batch)

        if len(combined) <= 4500:
            # Translate as one request
            translated = translator.translate(combined)
            # Split back
            parts = translated.split("|||")
            # Clean up and ensure same count
            parts = [p.strip() for p in parts]
            while len(parts) < len(batch):
                parts.append("")
            results.extend(parts[:len(batch)])
        else:
            # Too long, translate one by one
            for text in batch:
                try:
                    translated = translator.translate(text) if text.strip() else ""
                    results.append(translated)
                except Exception as e:
                    print(f"[Translator] Warning: failed to translate '{text[:50]}...': {e}")
                    results.append(text)  # Keep original on failure

    return results


def _estimate_word_timing(text: str, start: float, end: float) -> list[dict]:
    """
    Estimate word-level timing for translated text.
    Since translation changes word count, we distribute timing evenly.
    """
    words = text.split()
    if not words:
        return []

    duration = end - start
    word_duration = duration / len(words)

    result = []
    for i, word in enumerate(words):
        w_start = start + i * word_duration
        w_end = w_start + word_duration
        result.append({
            "word": word,
            "start": round(w_start, 3),
            "end": round(w_end, 3),
            "confidence": 0.9,  # estimated, not from STT
        })

    return result


def _normalize_lang_code(code: str) -> str:
    """Normalize language code to our standard."""
    code = code.lower().strip()
    # Map common variants
    mapping = {
        "english": "en",
        "vietnamese": "vi",
        "chinese": "zh",
        "italian": "it",
        "korean": "ko",
        "japanese": "ja",
        "zh-cn": "zh",
        "zh-tw": "zh",
        "cmn": "zh",  # Mandarin
    }
    return mapping.get(code, code)


def list_supported_languages() -> dict:
    """Return dict of supported language codes and names."""
    return {
        "en": "English",
        "vi": "Vietnamese (Tiếng Việt)",
        "zh": "Chinese (中文)",
        "it": "Italian (Italiano)",
        "ko": "Korean (한국어)",
        "ja": "Japanese (日本語)",
    }


def translate_srt(
    srt_path: str,
    output_path: str,
    target_lang: str,
    llm_endpoint: str = "http://localhost:20128/v1",
    source_lang: Optional[str] = None,
    model: str = "auto",
) -> str:
    """
    Translate SRT file using LLM (preserves timestamps exactly).
    
    Uses LLM to rewrite/translate subtitle text while keeping
    all timing information intact. Better quality than Google Translate
    for natural-sounding subtitles.
    
    Args:
        srt_path: Input SRT file path
        output_path: Output SRT file path
        target_lang: Target language code (en, vi, zh, it, ko, ja)
        llm_endpoint: LLM API endpoint (OpenAI-compatible)
        source_lang: Source language (None = auto-detect)
        model: Model name (auto = let endpoint decide)
    
    Returns:
        Path to translated SRT file
    """
    import requests

    # Read SRT content
    with open(srt_path, "r", encoding="utf-8") as f:
        srt_content = f.read()

    # Parse SRT to extract text blocks (keep structure)
    blocks = re.split(r"\n\s*\n", srt_content.strip())
    
    if not blocks:
        raise ValueError(f"No subtitle blocks found in: {srt_path}")

    target_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)
    source_name = SUPPORTED_LANGUAGES.get(source_lang, "the source language") if source_lang else "the source language"

    print(f"[Translator] Translating SRT via LLM: {source_name} → {target_name}")
    print(f"[Translator] {len(blocks)} subtitle blocks")

    # Process in batches to avoid token limits
    batch_size = 25
    translated_blocks = []

    for i in range(0, len(blocks), batch_size):
        batch = blocks[i:i + batch_size]
        
        # Extract just the text lines (skip index and timestamp lines)
        texts_to_translate = []
        block_structures = []
        
        for block in batch:
            lines = block.strip().split("\n")
            if len(lines) < 3:
                block_structures.append({"raw": block, "text_idx": None})
                continue
            
            # Lines: [index, timestamp, text...]
            index_line = lines[0]
            timestamp_line = lines[1]
            text_lines = "\n".join(lines[2:])
            
            block_structures.append({
                "index": index_line,
                "timestamp": timestamp_line,
                "text_idx": len(texts_to_translate),
            })
            texts_to_translate.append(text_lines)

        if not texts_to_translate:
            translated_blocks.extend(batch)
            continue

        # Call LLM for translation
        numbered_texts = "\n".join(f"{j+1}. {t}" for j, t in enumerate(texts_to_translate))
        
        prompt = f"""Translate the following numbered subtitle lines to {target_name}. 
Rules:
- Keep the same numbering
- Translate naturally (not word-by-word)
- Keep it concise (subtitles should be short)
- Do NOT add any explanation, just output the translations
- Format: one translation per line, numbered

{numbered_texts}"""

        try:
            translated_texts = _call_llm(prompt, llm_endpoint, model)
            # Parse numbered response
            parsed = _parse_numbered_response(translated_texts, len(texts_to_translate))
        except Exception as e:
            print(f"  [Translator] LLM failed for batch {i//batch_size + 1}, falling back to Google: {e}")
            # Fallback to Google Translate
            parsed = []
            for text in texts_to_translate:
                try:
                    translated = translate_text(text, source_lang or "en", target_lang)
                    parsed.append(translated)
                except Exception:
                    parsed.append(text)

        # Reconstruct blocks with translated text
        for struct in block_structures:
            if struct.get("text_idx") is not None:
                idx = struct["text_idx"]
                translated_text = parsed[idx] if idx < len(parsed) else texts_to_translate[idx]
                translated_blocks.append(f"{struct['index']}\n{struct['timestamp']}\n{translated_text}")
            elif "raw" in struct:
                translated_blocks.append(struct["raw"])

    # Write output SRT
    output_content = "\n\n".join(translated_blocks) + "\n"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_content)

    print(f"[Translator] Saved: {output_path}")
    return output_path


def _call_llm(prompt: str, endpoint: str, model: str = "gemini-2.5-flash") -> str:
    """Call LLM API (OpenAI-compatible) for translation. Model MUST be specified."""
    import requests

    url = f"{endpoint}/chat/completions"
    
    # Model must not be empty or "auto" — 9router requires explicit model
    if not model or model == "auto":
        from config.settings import get_settings
        model = get_settings().get("llm_model") or "gemini-2.5-flash"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a professional subtitle translator. Output only the translations, nothing else."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    
    resp = requests.post(url, json=payload, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _parse_numbered_response(response: str, expected_count: int) -> list[str]:
    """Parse numbered LLM response back into list of translations."""
    lines = response.strip().split("\n")
    results = []
    current_text = ""
    current_num = 0

    for line in lines:
        # Match numbered line: "1. text" or "1) text" or just "1 text"
        match = re.match(r"^\s*(\d+)[.):\s]\s*(.*)", line)
        if match:
            num = int(match.group(1))
            text = match.group(2).strip()
            
            # Save previous if exists
            if current_num > 0 and current_text:
                results.append(current_text)
            
            current_num = num
            current_text = text
        elif current_num > 0:
            # Continuation of previous line
            current_text += "\n" + line.strip()

    # Don't forget last one
    if current_text:
        results.append(current_text)

    # Pad if we got fewer results than expected
    while len(results) < expected_count:
        results.append("")

    return results[:expected_count]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python translator.py <transcript.json> <target_lang>")
        print(f"Supported languages: {list(list_supported_languages().keys())}")
        sys.exit(1)

    input_file = sys.argv[1]
    target = sys.argv[2]

    # Load transcript
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Translate
    result = translate_transcript(data, target)

    # Save
    from pathlib import Path
    output_file = f"{Path(input_file).stem}_{target}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Saved: {output_file}")
