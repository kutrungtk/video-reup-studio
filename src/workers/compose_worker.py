"""
Video Reup Studio Rebuild — Compose Worker
QThread worker for composing final video.
3 modes: video gốc (cắt theo SRT), clips (từ Visuals), timeline (từ Timeline Editor).
"""

import os
import sys
import shutil
import traceback
from PySide6.QtCore import QThread, Signal


class ComposeWorker(QThread):
    """Compose video in background."""

    progress = Signal(int, str)
    log_message = Signal(str)
    finished = Signal(str)  # output video path
    error = Signal(str)

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        self._cancelled = False

    def run(self):
        try:
            from config.constants import PROJECT_ROOT
            engine_dir = os.path.join(PROJECT_ROOT, "src", "engine")
            modules_dir = os.path.join(engine_dir, "modules")
            for p in [engine_dir, modules_dir]:
                if p not in sys.path:
                    sys.path.insert(0, p)

            mode = self._config.get("mode", "video")
            if mode == "video":
                self._compose_from_video()
            elif mode == "clips":
                self._compose_from_clips()
            elif mode == "timeline":
                self._compose_from_timeline()
            elif mode == "scenes":
                self._compose_from_scenes()

        except Exception as e:
            tb = traceback.format_exc()
            self.log_message.emit(f"❌ {str(e)}\n{tb}")
            self.error.emit(str(e))

    def _compose_from_timeline(self):
        """Mode 3: Compose from Timeline Editor clips."""
        from engine.modules.ffmpeg_utils import run_ffmpeg, concat_videos

        video_clips = self._config["video_clips"]
        audio_clips = self._config["audio_clips"]
        subtitle_clips = self._config.get("subtitle_clips", [])
        output_dir = self._config["output_dir"]
        os.makedirs(output_dir, exist_ok=True)

        total_steps = len(video_clips) + 3
        step = 0

        self.progress.emit(5, "Preparing segments...")
        segments_dir = os.path.join(output_dir, "timeline_segments")
        os.makedirs(segments_dir, exist_ok=True)

        prepared_clips = []
        for i, vclip in enumerate(video_clips):
            if self._cancelled:
                self.log_message.emit("⏹ Cancelled")
                return

            step += 1
            pct = int(5 + (step / total_steps) * 60)
            self.progress.emit(pct, f"Processing clip {i+1}/{len(video_clips)}...")

            video_path = vclip["path"]
            clip_start = vclip["start"]
            clip_end = vclip["end"]
            duration = clip_end - clip_start

            if not video_path or not os.path.isfile(video_path):
                self.log_message.emit(f"  ⚠ Skip clip {i+1}: file not found")
                continue

            ext = os.path.splitext(video_path)[1].lower()
            seg_output = os.path.join(segments_dir, f"seg_{i+1:03d}.mp4")

            matching_audio = None
            for aclip in audio_clips:
                if aclip["start"] < clip_end and aclip["end"] > clip_start:
                    if aclip["path"] and os.path.isfile(aclip["path"]):
                        matching_audio = aclip["path"]
                        break

            if ext in (".png", ".jpg", ".jpeg", ".webp"):
                self._image_to_video(video_path, seg_output, duration, matching_audio)
            elif ext in (".mp4", ".mkv", ".webm", ".avi"):
                self._video_segment(video_path, seg_output, duration, matching_audio)
            else:
                continue

            if os.path.isfile(seg_output):
                prepared_clips.append(seg_output)
                self.log_message.emit(f"  ✓ Clip {i+1}: {os.path.basename(video_path)} ({duration:.1f}s)")

        if not prepared_clips:
            self.error.emit("No clips were processed successfully")
            return

        self.progress.emit(70, f"Concatenating {len(prepared_clips)} segments...")
        concat_path = os.path.join(output_dir, "concat.mp4")
        transition = self._config.get("transition", "none")

        if transition != "none" and len(prepared_clips) > 1:
            try:
                from engine.modules.transitions import concat_with_transitions, TransitionConfig
                trans_config = TransitionConfig(transition_type=transition, duration=0.5)
                concat_with_transitions(prepared_clips, concat_path, trans_config)
            except ImportError:
                concat_videos(prepared_clips, concat_path)
        else:
            concat_videos(prepared_clips, concat_path)

        if not os.path.isfile(concat_path):
            self.error.emit("Concatenation failed")
            return

        final_path = os.path.join(output_dir, "composed_final.mp4")
        srt_path = self._config.get("srt_path")

        if self._config.get("burn_subtitle") and srt_path and os.path.isfile(srt_path):
            self.progress.emit(85, "Burning subtitle...")
            try:
                from engine.modules.ffmpeg_utils import burn_subtitle
                burn_subtitle(concat_path, srt_path, final_path)
            except Exception as e:
                self.log_message.emit(f"  ⚠ Subtitle burn failed: {e}")
                shutil.copy2(concat_path, final_path)
        else:
            shutil.copy2(concat_path, final_path)

        self.progress.emit(100, "Done!")
        self.log_message.emit(f"\n✅ Output: {final_path}")
        self.finished.emit(final_path)

    def _compose_from_scenes(self):
        """Mode 4: Compose from Scene-based timeline (scene cards)."""
        from engine.modules.ffmpeg_utils import run_ffmpeg, concat_videos

        scenes = self._config["scenes"]
        output_dir = self._config["output_dir"]
        os.makedirs(output_dir, exist_ok=True)

        total = len(scenes)
        self.progress.emit(5, f"Processing {total} scenes...")
        segments_dir = os.path.join(output_dir, "scene_segments")
        os.makedirs(segments_dir, exist_ok=True)

        prepared_clips = []
        for i, scene in enumerate(scenes):
            if self._cancelled:
                self.log_message.emit("⏹ Cancelled")
                return

            pct = int(5 + ((i + 1) / total) * 65)
            self.progress.emit(pct, f"Scene {i+1}/{total}...")

            visual_path = scene.get("visual_path", "")
            voice_path = scene.get("voice_path", "")
            duration = scene.get("duration", 5.0)
            visual_type = scene.get("visual_type", "none")

            seg_output = os.path.join(segments_dir, f"scene_{i+1:03d}.mp4")

            # Determine audio source
            audio_path = voice_path if voice_path and os.path.isfile(voice_path) else None

            if visual_type == "image" and visual_path and os.path.isfile(visual_path):
                # Image → video with Ken Burns + voice
                self._image_to_video(visual_path, seg_output, duration, audio_path)
            elif visual_type == "video" and visual_path and os.path.isfile(visual_path):
                # Video clip → trim + replace audio
                self._video_segment(visual_path, seg_output, duration, audio_path)
            elif audio_path:
                # No visual but has voice → black screen + voice
                self._black_with_audio(seg_output, duration, audio_path)
            else:
                # Skip scene with nothing
                self.log_message.emit(f"  ⚠ Scene {i+1}: no visual or voice, skipped")
                continue

            if os.path.isfile(seg_output):
                prepared_clips.append(seg_output)
                vname = os.path.basename(visual_path) if visual_path else "no visual"
                has_voice = "🔊" if audio_path else "🔇"
                self.log_message.emit(f"  ✓ Scene {i+1}: {vname} {has_voice} ({duration:.1f}s)")

        if not prepared_clips:
            self.error.emit("No scenes were processed successfully")
            return

        # Concatenate
        self.progress.emit(75, f"Concatenating {len(prepared_clips)} scenes...")
        concat_path = os.path.join(output_dir, "concat.mp4")
        transition = self._config.get("transition", "none")

        if transition != "none" and len(prepared_clips) > 1:
            try:
                from engine.modules.transitions import concat_with_transitions, TransitionConfig
                trans_config = TransitionConfig(transition_type=transition, duration=0.5)
                concat_with_transitions(prepared_clips, concat_path, trans_config)
            except ImportError:
                self.log_message.emit("  ⚠ Transitions module not found, simple concat")
                concat_videos(prepared_clips, concat_path)
        else:
            concat_videos(prepared_clips, concat_path)

        if not os.path.isfile(concat_path):
            self.error.emit("Concatenation failed")
            return

        self.log_message.emit(f"  ✓ Concatenated {len(prepared_clips)} scenes")

        # Burn subtitle
        final_path = os.path.join(output_dir, "composed_final.mp4")
        srt_path = self._config.get("srt_path")

        if self._config.get("burn_subtitle") and srt_path and os.path.isfile(srt_path):
            self.progress.emit(88, "Burning subtitle...")
            try:
                from engine.modules.ffmpeg_utils import burn_subtitle
                burn_subtitle(concat_path, srt_path, final_path)
                self.log_message.emit("  ✓ Subtitle burned")
            except Exception as e:
                self.log_message.emit(f"  ⚠ Subtitle burn failed: {e}, using concat")
                shutil.copy2(concat_path, final_path)
        else:
            shutil.copy2(concat_path, final_path)

        self.progress.emit(100, "Done!")
        self.log_message.emit(f"\n✅ Output: {final_path}")
        self.finished.emit(final_path)

    def _black_with_audio(self, output: str, duration: float, audio_path: str):
        """Generate black video with audio (for scenes without visual)."""
        from engine.modules.ffmpeg_utils import run_ffmpeg
        duration = max(0.5, duration)
        run_ffmpeg([
            "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:d={duration}:r=25",
            "-i", audio_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-pix_fmt", "yuv420p",
            "-y", output,
        ])

    def _image_to_video(self, image_path: str, output: str, duration: float, audio_path: str = None):
        """Convert image to video clip with zoom effect."""
        from engine.modules.ffmpeg_utils import run_ffmpeg

        duration = max(0.5, duration)
        # Ken Burns zoom-in effect
        cmd = [
            "-loop", "1", "-i", image_path,
            "-vf", f"zoompan=z='min(zoom+0.001,1.3)':d={int(duration*25)}:s=1920x1080:fps=25",
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "fast", "-crf", "23",
        ]

        if audio_path:
            cmd.extend(["-i", audio_path, "-c:a", "aac", "-b:a", "192k", "-shortest"])
        else:
            cmd.extend(["-an"])

        cmd.extend(["-y", output])
        run_ffmpeg(cmd)

    def _video_segment(self, video_path: str, output: str, duration: float, audio_path: str = None):
        """Trim video and optionally replace audio."""
        from engine.modules.ffmpeg_utils import run_ffmpeg

        duration = max(0.5, duration)
        if audio_path:
            # Replace audio with voice
            cmd = [
                "-i", video_path,
                "-i", audio_path,
                "-t", str(duration),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                "-y", output,
            ]
        else:
            # Just trim video
            cmd = [
                "-i", video_path,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "copy",
                "-y", output,
            ]
        run_ffmpeg(cmd)

    def _compose_from_video(self):
        """Mode 1: Cắt video gốc theo SRT → ghép voice → sub."""
        from engine.modules.video_cutter import parse_srt, cut_video_by_segments
        from engine.modules.composer import compose_all_segments, ComposeConfig

        video_path = self._config["video_path"]
        srt_path = self._config["srt_path"]
        voice_dir = self._config["voice_dir"]
        output_dir = self._config["output_dir"]
        os.makedirs(output_dir, exist_ok=True)

        self.progress.emit(5, "Loading segments...")
        segments = parse_srt(srt_path)
        if not segments:
            self.error.emit("No segments in SRT")
            return

        # Assign voice paths
        self._assign_voice_paths(segments, voice_dir)
        voiced = sum(1 for s in segments if s.voice_path)
        self.log_message.emit(f"Segments: {len(segments)}, Voiced: {voiced}")

        # Cut video by SRT
        self.progress.emit(20, "Cutting video by SRT timestamps...")
        video_seg_dir = os.path.join(output_dir, "video_segments")
        segments = cut_video_by_segments(
            video_path=video_path,
            segments=segments,
            output_dir=video_seg_dir,
            crop_percent=0.03,
            re_encode=True,
        )
        self.log_message.emit(f"Cut {len(segments)} video segments")

        # Compose
        self.progress.emit(50, "Composing segments (voice + video)...")
        compose_config = ComposeConfig(
            mismatch_strategy=self._config.get("mismatch", "freeze_last"),
            burn_subtitle=self._config.get("burn_subtitle", True),
            transition_type=self._config.get("transition", "none"),
        )

        final_path = os.path.join(output_dir, "composed_final.mp4")
        subtitle_path = srt_path if self._config.get("burn_subtitle") else None

        compose_all_segments(
            segments=segments,
            output_dir=output_dir,
            final_output=final_path,
            config=compose_config,
            subtitle_path=subtitle_path,
        )

        self.progress.emit(100, "Done!")
        self.log_message.emit(f"\n✅ Output: {final_path}")
        self.finished.emit(final_path)

    def _compose_from_clips(self):
        """Mode 2: Ghép clips (từ Visuals) + voice → final video."""
        from engine.modules.video_cutter import parse_srt
        from engine.modules.ffmpeg_utils import run_ffmpeg, concat_videos

        clips_dir = self._config["clips_dir"]
        srt_path = self._config["srt_path"]
        voice_dir = self._config["voice_dir"]
        output_dir = self._config["output_dir"]
        os.makedirs(output_dir, exist_ok=True)

        self.progress.emit(5, "Loading segments and clips...")

        segments = parse_srt(srt_path)
        if not segments:
            self.error.emit("No segments in SRT")
            return

        # Find clips (scene_001.mp4, scene_002.mp4, ...)
        clip_files = sorted([
            os.path.join(clips_dir, f) for f in os.listdir(clips_dir)
            if f.endswith(".mp4") and f.startswith("scene_")
        ])

        if not clip_files:
            self.error.emit(f"No clips found in {clips_dir}")
            return

        self.log_message.emit(f"Found {len(clip_files)} clips, {len(segments)} segments")

        # Assign voice paths
        self._assign_voice_paths(segments, voice_dir)

        # Merge voice into each clip
        self.progress.emit(20, "Merging voice into clips...")
        merged_dir = os.path.join(output_dir, "merged")
        os.makedirs(merged_dir, exist_ok=True)

        merged_clips = []
        for i, clip_path in enumerate(clip_files):
            if self._cancelled:
                self.log_message.emit("⏹ Cancelled")
                return

            merged_path = os.path.join(merged_dir, f"merged_{i+1:03d}.mp4")

            # Find matching voice
            voice_path = None
            if i < len(segments) and segments[i].voice_path:
                voice_path = segments[i].voice_path
            else:
                for ext in [".wav", ".mp3"]:
                    vp = os.path.join(voice_dir, f"seg_{i+1:03d}{ext}")
                    if os.path.isfile(vp):
                        voice_path = vp
                        break

            if voice_path and os.path.isfile(voice_path):
                run_ffmpeg([
                    "-i", clip_path,
                    "-i", voice_path,
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-shortest",
                    "-y", merged_path,
                ])
            else:
                shutil.copy2(clip_path, merged_path)

            merged_clips.append(merged_path)
            self.log_message.emit(f"  [{i+1}] {'+ voice' if voice_path else 'no voice'}")

        # Concat all merged clips
        self.progress.emit(60, f"Concatenating {len(merged_clips)} clips...")

        concat_path = os.path.join(output_dir, "concat.mp4")
        transition = self._config.get("transition", "none")

        if transition != "none" and len(merged_clips) > 1:
            try:
                from engine.modules.transitions import concat_with_transitions, TransitionConfig
                trans_config = TransitionConfig(transition_type=transition, duration=0.5)
                concat_with_transitions(merged_clips, concat_path, trans_config)
            except ImportError:
                concat_videos(merged_clips, concat_path)
        else:
            concat_videos(merged_clips, concat_path)

        self.log_message.emit(f"Concatenated → {concat_path}")

        # Burn subtitle
        final_path = os.path.join(output_dir, "composed_final.mp4")
        if self._config.get("burn_subtitle") and os.path.isfile(srt_path):
            self.progress.emit(80, "Burning subtitle...")
            try:
                from engine.modules.ffmpeg_utils import burn_subtitle
                burn_subtitle(concat_path, srt_path, final_path)
            except Exception as e:
                self.log_message.emit(f"  ⚠ Subtitle burn failed: {e}")
                shutil.copy2(concat_path, final_path)
        else:
            shutil.copy2(concat_path, final_path)

        self.progress.emit(100, "Done!")
        self.log_message.emit(f"\n✅ Output: {final_path}")
        self.finished.emit(final_path)

    def _assign_voice_paths(self, segments, voice_dir):
        """Assign voice file paths to segments."""
        for seg in segments:
            for ext in [".wav", ".mp3"]:
                vp = os.path.join(voice_dir, f"seg_{seg.index:03d}{ext}")
                if os.path.isfile(vp):
                    seg.voice_path = vp
                    break
