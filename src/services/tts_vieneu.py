"""
Video Reup Studio Rebuild — TTS VieNeu Service
Vietnamese voice cloning offline using VieNeu library.
Learned from NAVTools tts_vieneu.py.
"""

import os
import threading
from typing import Optional

from engine.modules.ffmpeg_utils import run_ffmpeg


# Lock for thread-safe model access (VieNeu is single-threaded)
_model_lock = threading.Lock()
_tts_instance = None
_voice_cache: dict[str, object] = {}


def get_tts():
    """Get or create VieNeu TTS instance (singleton)."""
    global _tts_instance
    if _tts_instance is None:
        with _model_lock:
            if _tts_instance is None:
                try:
                    from vieneu import Vieneu
                    _tts_instance = Vieneu(mode="turbo", device="cpu")
                    print("[VieNeu] Model loaded (turbo, CPU)")
                except ImportError:
                    raise RuntimeError(
                        "VieNeu not installed. Install: "
                        "pip install vieneu --extra-index-url https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/"
                    )
    return _tts_instance


def encode_voice_reference(audio_path: str) -> object:
    """
    Encode a voice reference file for cloning.
    Caches result for reuse.
    
    Args:
        audio_path: Path to reference audio (mp3/wav, ~8s recommended)
    
    Returns:
        Encoded voice object for synthesis
    """
    global _voice_cache

    if audio_path in _voice_cache:
        return _voice_cache[audio_path]

    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Voice reference not found: {audio_path}")

    # Extract 8-second clip, mono, 24kHz (optimal for VieNeu)
    import tempfile
    temp_clip = tempfile.mktemp(suffix=".wav")

    try:
        run_ffmpeg([
            "-y",
            "-ss", "1",           # skip first second
            "-i", audio_path,
            "-t", "8",            # 8 seconds
            "-ac", "1",           # mono
            "-ar", "24000",       # 24kHz
            "-c:a", "pcm_s16le", # PCM 16-bit
            "-vn",                # no video
            temp_clip,
        ])

        tts = get_tts()
        with _model_lock:
            encoded = tts.encode_reference(temp_clip)

        _voice_cache[audio_path] = encoded
        print(f"[VieNeu] Voice encoded: {os.path.basename(audio_path)}")
        return encoded

    finally:
        if os.path.exists(temp_clip):
            os.remove(temp_clip)


def synthesize(
    text: str,
    output_path: str,
    voice_ref: Optional[str] = None,
    voice_preset: str = "male",
) -> str:
    """
    Synthesize Vietnamese speech from text.
    
    Args:
        text: Vietnamese text to speak
        output_path: Output WAV path
        voice_ref: Path to custom voice reference file (for cloning)
        voice_preset: "male" or "female" (used if voice_ref is None)
    
    Returns:
        Path to output WAV
    """
    tts = get_tts()

    # Get voice encoding
    if voice_ref and os.path.isfile(voice_ref):
        voice = encode_voice_reference(voice_ref)
    else:
        # Use bundled preset voices
        voice = _get_preset_voice(voice_preset)

    # Synthesize
    with _model_lock:
        audio = tts.infer(text=text, voice=voice)
        tts.save(audio, output_path)

    return output_path


def synthesize_segments(
    segments: list,
    output_dir: str,
    voice_ref: Optional[str] = None,
    voice_preset: str = "male",
    progress_cb=None,
) -> list:
    """
    Synthesize voice for multiple segments (SRT entries).
    
    Args:
        segments: List of Segment objects with .text and .index
        output_dir: Directory to save WAV files
        voice_ref: Custom voice reference
        voice_preset: "male" or "female"
        progress_cb: Callback(percent, message)
    
    Returns:
        Updated segments with .voice_path set
    """
    os.makedirs(output_dir, exist_ok=True)
    total = len(segments)

    print(f"[VieNeu] Synthesizing {total} segments...")

    for i, seg in enumerate(segments):
        if not seg.text.strip():
            continue

        output_path = os.path.join(output_dir, f"seg_{seg.index:03d}.wav")

        try:
            synthesize(seg.text, output_path, voice_ref=voice_ref, voice_preset=voice_preset)
            seg.voice_path = output_path
        except Exception as e:
            print(f"  [VieNeu] Segment {seg.index} failed: {e}")
            seg.voice_path = None

        if progress_cb and total > 0:
            progress_cb(int((i + 1) / total * 100), f"VieNeu TTS: {i+1}/{total}")

    voiced = sum(1 for s in segments if s.voice_path and os.path.isfile(s.voice_path))
    print(f"[VieNeu] Done: {voiced}/{total} segments")
    return segments


def merge_voice_to_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    replace: bool = True,
) -> str:
    """
    Merge synthesized voice into video.
    
    Args:
        video_path: Input video
        audio_path: Voice WAV/MP3
        output_path: Output video
        replace: True = replace original audio, False = mix
    """
    if replace:
        run_ffmpeg([
            "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_path,
        ])
    else:
        # Mix original + new voice
        run_ffmpeg([
            "-y",
            "-i", video_path,
            "-i", audio_path,
            "-filter_complex",
            "[0:a]volume=0.2[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first[aout]",
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path,
        ])

    return output_path


def _get_preset_voice(preset: str) -> object:
    """Get bundled preset voice (male/female)."""
    from config.constants import ASSETS_DIR

    voice_refs = {
        "male": os.path.join(ASSETS_DIR, "voice_refs", "minhquan.mp3"),
        "female": os.path.join(ASSETS_DIR, "voice_refs", "ngochuyen.mp3"),
    }

    ref_path = voice_refs.get(preset, voice_refs["male"])

    if not os.path.isfile(ref_path):
        raise FileNotFoundError(
            f"Voice preset '{preset}' not found at {ref_path}. "
            f"Copy voice reference files to assets/voice_refs/"
        )

    return encode_voice_reference(ref_path)


def list_voices() -> dict:
    """List available voice presets."""
    from config.constants import ASSETS_DIR

    voices = {}
    voice_dir = os.path.join(ASSETS_DIR, "voice_refs")

    if os.path.isdir(voice_dir):
        for f in os.listdir(voice_dir):
            if f.endswith((".mp3", ".wav")):
                name = os.path.splitext(f)[0]
                voices[name] = os.path.join(voice_dir, f)

    return voices


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python tts_vieneu.py <text> <output.wav> [--voice male|female|path.mp3]")
        print("Requires: pip install vieneu")
        sys.exit(1)

    text = sys.argv[1]
    output = sys.argv[2]
    voice_ref = None
    voice_preset = "male"

    for i, arg in enumerate(sys.argv):
        if arg == "--voice" and i + 1 < len(sys.argv):
            v = sys.argv[i + 1]
            if os.path.isfile(v):
                voice_ref = v
            else:
                voice_preset = v

    synthesize(text, output, voice_ref=voice_ref, voice_preset=voice_preset)
    print(f"Output: {output}")
