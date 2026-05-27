"""
Video Reup Studio - Transcriber Module
Speech-to-Text using faster-whisper (WhisperX) with word-level timestamps.
Fallback: YouTube subtitle download.
"""

import json
import os
import tempfile
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

from modules.ffmpeg_utils import extract_audio, get_video_info


@dataclass
class WordSegment:
    """Single word with timing."""
    word: str
    start: float
    end: float
    confidence: float = 1.0


@dataclass
class Segment:
    """A sentence/phrase segment with word-level detail."""
    id: int
    text: str
    start: float
    end: float
    words: list[WordSegment]
    language: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Transcript:
    """Full transcript with segments and metadata."""
    segments: list[Segment]
    language: str
    duration: float
    source: str  # "whisper" or "youtube"

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "duration": self.duration,
            "source": self.source,
            "segments": [
                {
                    "id": seg.id,
                    "text": seg.text,
                    "start": seg.start,
                    "end": seg.end,
                    "words": [
                        {"word": w.word, "start": w.start, "end": w.end, "confidence": w.confidence}
                        for w in seg.words
                    ],
                }
                for seg in self.segments
            ],
        }

    def to_srt(self) -> str:
        """Export as SRT subtitle format."""
        lines = []
        for seg in self.segments:
            start_ts = _seconds_to_srt_time(seg.start)
            end_ts = _seconds_to_srt_time(seg.end)
            lines.append(f"{seg.id}")
            lines.append(f"{start_ts} --> {end_ts}")
            lines.append(seg.text)
            lines.append("")
        return "\n".join(lines)

    def save_json(self, output_path: str):
        """Save transcript as JSON."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def save_srt(self, output_path: str):
        """Save transcript as SRT."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(self.to_srt())

    @classmethod
    def from_json(cls, json_path: str) -> "Transcript":
        """Load transcript from JSON file."""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        segments = []
        for seg_data in data["segments"]:
            words = [
                WordSegment(
                    word=w["word"],
                    start=w["start"],
                    end=w["end"],
                    confidence=w.get("confidence", 1.0),
                )
                for w in seg_data.get("words", [])
            ]
            segments.append(Segment(
                id=seg_data["id"],
                text=seg_data["text"],
                start=seg_data["start"],
                end=seg_data["end"],
                words=words,
            ))
        return cls(
            segments=segments,
            language=data["language"],
            duration=data["duration"],
            source=data.get("source", "unknown"),
        )


def transcribe_whisper(
    video_path: str,
    model_size: str = "large-v3",
    language: Optional[str] = None,
    device: str = "cuda",
    compute_type: str = "float16",
) -> Transcript:
    """
    Transcribe video using faster-whisper with word-level timestamps.
    
    Args:
        video_path: Path to video/audio file
        model_size: Whisper model (tiny, base, small, medium, large-v3)
        language: Source language code (None = auto-detect)
        device: "cuda" or "cpu"
        compute_type: "float16" (GPU) or "int8" (CPU)
    """
    from faster_whisper import WhisperModel

    # Extract audio for Whisper (16kHz mono WAV)
    temp_audio = tempfile.mktemp(suffix=".wav")
    try:
        extract_audio(video_path, temp_audio, sample_rate=16000)

        # Load model
        model = WhisperModel(model_size, device=device, compute_type=compute_type)

        # Transcribe with word timestamps
        segments_gen, info = model.transcribe(
            temp_audio,
            language=language,
            word_timestamps=True,
            vad_filter=True,  # Voice Activity Detection for better accuracy
        )

        # Parse segments
        segments = []
        for i, seg in enumerate(segments_gen, 1):
            words = []
            if seg.words:
                for w in seg.words:
                    words.append(WordSegment(
                        word=w.word.strip(),
                        start=round(w.start, 3),
                        end=round(w.end, 3),
                        confidence=round(w.probability, 3) if w.probability else 1.0,
                    ))

            segments.append(Segment(
                id=i,
                text=seg.text.strip(),
                start=round(seg.start, 3),
                end=round(seg.end, 3),
                words=words,
                language=info.language,
            ))

        # Get video duration
        video_info = get_video_info(video_path)

        return Transcript(
            segments=segments,
            language=info.language,
            duration=video_info.duration,
            source="whisper",
        )

    finally:
        if os.path.exists(temp_audio):
            os.remove(temp_audio)


def transcribe_youtube(video_url: str, language: str = "en") -> Optional[Transcript]:
    """
    Try to download existing subtitles from YouTube.
    Fallback method - faster but less accurate than Whisper.
    
    Args:
        video_url: YouTube video URL
        language: Preferred subtitle language
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        import re

        # Extract video ID from URL
        match = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", video_url)
        if not match:
            return None
        video_id = match.group(1)

        # Try to get transcript
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Try manual first, then auto-generated
            transcript = None
            try:
                transcript = transcript_list.find_manually_created_transcript([language])
            except Exception:
                try:
                    transcript = transcript_list.find_generated_transcript([language])
                except Exception:
                    return None

            if not transcript:
                return None

            entries = transcript.fetch()

        except Exception:
            return None

        # Convert to our format
        segments = []
        for i, entry in enumerate(entries, 1):
            start = entry["start"]
            duration = entry["duration"]
            text = entry["text"].replace("\n", " ").strip()

            if not text:
                continue

            segments.append(Segment(
                id=i,
                text=text,
                start=round(start, 3),
                end=round(start + duration, 3),
                words=[],  # YouTube doesn't provide word-level timing
            ))

        if not segments:
            return None

        total_duration = segments[-1].end if segments else 0

        return Transcript(
            segments=segments,
            language=language,
            duration=total_duration,
            source="youtube",
        )

    except ImportError:
        print("youtube-transcript-api not installed. Skipping YouTube fallback.")
        return None


def transcribe(
    input_path: str,
    model_size: str = "large-v3",
    language: Optional[str] = None,
    device: str = "cuda",
    youtube_url: Optional[str] = None,
    prefer_youtube: bool = True,
) -> Transcript:
    """
    Main transcription function with smart fallback.
    
    Priority:
    1. If YouTube URL provided and prefer_youtube=True → try YouTube sub first
    2. If YouTube fails or not available → use Whisper (local GPU)
    
    Args:
        input_path: Path to video file
        model_size: Whisper model size
        language: Source language (None = auto-detect)
        device: "cuda" or "cpu"
        youtube_url: Optional YouTube URL for subtitle download
        prefer_youtube: Try YouTube subtitles first (faster)
    """
    # Try YouTube first if URL provided
    if youtube_url and prefer_youtube:
        print("[Transcriber] Trying YouTube subtitles...")
        yt_transcript = transcribe_youtube(youtube_url, language or "en")
        if yt_transcript and len(yt_transcript.segments) > 0:
            print(f"[Transcriber] Got YouTube subs: {len(yt_transcript.segments)} segments")
            return yt_transcript
        print("[Transcriber] YouTube subs not available, falling back to Whisper...")

    # Whisper transcription
    print(f"[Transcriber] Running Whisper ({model_size}) on {device}...")
    transcript = transcribe_whisper(
        video_path=input_path,
        model_size=model_size,
        language=language,
        device=device,
    )
    print(f"[Transcriber] Done: {len(transcript.segments)} segments, language={transcript.language}")
    return transcript


def _seconds_to_srt_time(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python transcriber.py <video_path> [--language en] [--model medium]")
        sys.exit(1)

    video = sys.argv[1]
    lang = None
    model = "large-v3"

    # Parse args
    for i, arg in enumerate(sys.argv):
        if arg == "--language" and i + 1 < len(sys.argv):
            lang = sys.argv[i + 1]
        elif arg == "--model" and i + 1 < len(sys.argv):
            model = sys.argv[i + 1]

    result = transcribe(video, model_size=model, language=lang)

    # Save outputs
    output_base = Path(video).stem
    result.save_json(f"{output_base}_transcript.json")
    result.save_srt(f"{output_base}_transcript.srt")
    print(f"Saved: {output_base}_transcript.json, {output_base}_transcript.srt")
