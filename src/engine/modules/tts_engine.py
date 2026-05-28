"""
Video Reup Studio Rebuild — TTS Engine
OmniVoice (primary, CUDA, voice clone, 646 languages) + Edge-TTS (fallback, free).
OmniVoice called via CLI: python -m omnivoice.cli.infer
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from typing import Optional
from dataclasses import dataclass

from engine.modules.ffmpeg_utils import run_ffprobe


# Edge-TTS voices per language
EDGE_VOICES = {
    "en": "en-US-GuyNeural",
    "it": "it-IT-DiegoNeural",
    "vi": "vi-VN-NamMinhNeural",
    "zh": "zh-CN-YunxiNeural",
    "ko": "ko-KR-InJoonNeural",
    "ja": "ja-JP-KeitaNeural",
}


@dataclass
class VoiceConfig:
    """Voice generation configuration."""
    engine: str = "omnivoice"       # omnivoice | edge-tts
    language: str = "it"
    speed: float = 1.0
    ref_audio: str = ""             # Path to reference audio for voice clone (3s+)
    instruct: str = ""              # Style instruction (e.g. "speak clearly")
    edge_voice: str = ""            # Edge-TTS voice ID override
    device: str = "cuda"


def generate_voice_per_segment(
    segments: list,
    output_dir: str,
    config: VoiceConfig = None,
    progress_cb=None,
    check_cancelled=None,
) -> list:
    """
    Generate voice for each segment.
    
    Args:
        segments: List of Segment objects with .text, .index
        output_dir: Directory to save voice files
        config: VoiceConfig options
        progress_cb: Callback(percent, message)
        check_cancelled: Callable that raises InterruptedError if cancelled
    
    Returns:
        Updated segments with .voice_path set
    """
    if config is None:
        config = VoiceConfig()

    os.makedirs(output_dir, exist_ok=True)
    total = len(segments)
    success_count = 0

    print(f"[TTS] Engine: {config.engine}, Language: {config.language}, Speed: {config.speed}")
    if config.ref_audio:
        print(f"[TTS] Voice clone ref: {config.ref_audio}")
    if config.instruct:
        print(f"[TTS] Instruct: {config.instruct}")

    for i, seg in enumerate(segments):
        if check_cancelled:
            check_cancelled()

        if not seg.text.strip():
            continue

        output_path = os.path.join(output_dir, f"seg_{seg.index:03d}.wav")

        if config.engine == "omnivoice":
            ok = _run_omnivoice(
                text=seg.text,
                output_path=output_path,
                language=config.language,
                speed=config.speed,
                ref_audio=config.ref_audio,
                instruct=config.instruct,
                device=config.device,
            )
            if ok:
                seg.voice_path = output_path
                success_count += 1
            else:
                # Fallback to Edge-TTS
                print(f"  [{seg.index}] OmniVoice failed, trying Edge-TTS...")
                edge_path = os.path.join(output_dir, f"seg_{seg.index:03d}.mp3")
                ok = _run_edge_tts(seg.text, edge_path, config.language, config.edge_voice, config.speed)
                if ok:
                    seg.voice_path = edge_path
                    success_count += 1
                else:
                    seg.voice_path = None
        else:
            # Edge-TTS
            edge_path = os.path.join(output_dir, f"seg_{seg.index:03d}.mp3")
            ok = _run_edge_tts(seg.text, edge_path, config.language, config.edge_voice, config.speed)
            if ok:
                seg.voice_path = edge_path
                success_count += 1
            else:
                seg.voice_path = None

        if progress_cb:
            progress_cb(int((i + 1) / total * 100), f"TTS: {i+1}/{total} ({config.engine})")

    print(f"[TTS] Done: {success_count}/{total} segments voiced")
    return segments


def _run_omnivoice(
    text: str,
    output_path: str,
    language: str = "it",
    speed: float = 1.0,
    ref_audio: str = "",
    instruct: str = "",
    device: str = "cuda",
) -> bool:
    """
    Run OmniVoice CLI for a single segment.
    Returns True if successful.
    """
    # Write text to temp file (avoid shell escaping issues)
    text_file = tempfile.mktemp(suffix=".txt", prefix="omni_")
    try:
        with open(text_file, "w", encoding="utf-8") as f:
            f.write(text.strip())

        # Build Python script that calls omnivoice
        script = f"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import subprocess, os

text_file = r'{text_file}'
output_file = r'{output_path}'

with open(text_file, 'r', encoding='utf-8') as f:
    text = f.read().strip()

cmd = [
    sys.executable, '-m', 'omnivoice.cli.infer',
    '--text', text,
    '--output', output_file,
    '--language', '{language}',
    '--device', '{device}',
    '--speed', '{speed}',
]
"""
        if ref_audio and os.path.isfile(ref_audio):
            script += f"cmd.extend(['--ref_audio', r'{ref_audio}'])\n"

        if instruct:
            safe_instruct = instruct.replace('"', '\\"')
            script += f'cmd.extend(["--instruct", "{safe_instruct}"])\n'

        script += """
result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=120)
if result.returncode == 0 and os.path.isfile(output_file):
    size_kb = os.path.getsize(output_file) // 1024
    print(f'OK:{size_kb}KB')
else:
    print(f'FAIL:{result.stderr[-200:] if result.stderr else "unknown"}', file=sys.stderr)
    sys.exit(1)
"""
        script_path = tempfile.mktemp(suffix=".py", prefix="omni_script_")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        # Run
        python = _find_python()
        result = subprocess.run(
            [python, script_path],
            capture_output=True, text=True, timeout=120,
        )

        # Cleanup script
        for f in [script_path, text_file]:
            if os.path.exists(f):
                os.remove(f)

        return result.returncode == 0 and os.path.isfile(output_path)

    except Exception as e:
        print(f"  [OmniVoice] Error: {e}")
        return False
    finally:
        if os.path.exists(text_file):
            os.remove(text_file)


def _run_edge_tts(
    text: str,
    output_path: str,
    language: str = "it",
    voice_override: str = "",
    speed: float = 1.0,
) -> bool:
    """Run Edge-TTS for a single segment."""
    try:
        import edge_tts

        voice = voice_override or EDGE_VOICES.get(language[:2], "en-US-GuyNeural")

        # Calculate rate string
        if speed > 1.0:
            rate = f"+{int((speed - 1.0) * 100)}%"
        elif speed < 1.0:
            rate = f"-{int((1.0 - speed) * 100)}%"
        else:
            rate = "+0%"

        async def _generate():
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(output_path)

        asyncio.run(_generate())
        return os.path.isfile(output_path) and os.path.getsize(output_path) > 0

    except Exception as e:
        print(f"  [Edge-TTS] Error: {e}")
        return False


def get_audio_duration(audio_path: str) -> float:
    """Get duration of audio file in seconds."""
    try:
        data = run_ffprobe(["-show_format", audio_path])
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def _find_python() -> str:
    """Find Python executable."""
    # Try current interpreter
    python = sys.executable
    if python and os.path.isfile(python):
        return python
    # Fallback
    import shutil
    return shutil.which("python") or shutil.which("python3") or "python"


if __name__ == "__main__":
    print("TTS Engine — OmniVoice + Edge-TTS")
    print("OmniVoice: python -m omnivoice.cli.infer --text '...' --output out.wav --language it --device cuda")
    print("  --ref_audio ref.wav  (voice clone, 3s+ reference)")
    print("  --instruct 'speak slowly'  (style control)")
    print("  --speed 1.0")
    print("Edge-TTS: free, fast, no GPU needed")
