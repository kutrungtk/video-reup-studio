# Video Reup Studio Rebuild — Hướng dẫn sử dụng & Cấu hình

## Mục đích Tool

**Video Reup Studio** là tool tự động reup video từ YouTube/nguồn khác lên TikTok/Facebook/YouTube.
Workflow: Tải video gốc → Dịch/viết lại kịch bản → Clone giọng nói → Tạo video mới → Export.

---

## Cài đặt cần thiết (Settings)

### Tab 1: 🤖 LLM / AI

| Setting | Giá trị | Mục đích |
|---------|---------|----------|
| API Endpoint | `http://localhost:20128/v1` | 9router local — dùng để rewrite kịch bản, dịch sub |
| API Key | (để trống nếu local) | Chỉ cần nếu dùng API remote |
| Text Model | `auto` | Model dùng để rewrite/dịch subtitle. "auto" = 9router tự chọn |
| Temperature | `0.3` | Thấp = dịch chính xác. Cao = sáng tạo hơn |
| Max Tokens | `4096` | Giới hạn output cho mỗi lần gọi LLM |
| Image API Endpoint | `http://localhost:20128/v1` | Endpoint tạo ảnh AI (khi cần thay thế segment bằng ảnh) |
| Image Model | `auto` | Model tạo ảnh (dall-e-3, flux, imagen...) |
| Image Resolution | `1080x1920` | Kích thước ảnh AI tạo ra |
| Style Prefix | `cinematic, dramatic lighting, 4k` | Prefix thêm vào prompt tạo ảnh |
| Gemini API Key | (optional) | Dùng cho vision analysis, scene detection |

### Tab 2: 🎙 Voice / TTS

| Setting | Giá trị | Mục đích |
|---------|---------|----------|
| Default Engine | `OmniVoice (CUDA)` | Engine mặc định. OmniVoice = clone giọng, Edge-TTS = free/nhanh |
| OmniVoice URL | `http://localhost:8100/tts` | (nếu dùng server mode thay vì CLI) |
| Default Voice | `it-IT-DiegoNeural` | Voice mặc định cho Edge-TTS |
| Voice Speed | `+0%` | Tốc độ nói (Edge-TTS) |
| Whisper Model | `large-v3` | Model transcribe. large-v3 = chính xác nhất |
| Device | `cuda` | GPU cho Whisper + OmniVoice |
| Source Language | `Auto-detect` | Ngôn ngữ video gốc |

### Tab 3: ⚡ Pipeline

| Setting | Giá trị | Mục đích |
|---------|---------|----------|
| Target Language | `Italian (it)` | Ngôn ngữ đích để dịch/rewrite |
| Platform | `TikTok` | Platform xuất video (ảnh hưởng resolution + duration) |
| Anti-Reup Preset | `Medium` | Mức độ anti-reup (light/medium/heavy) |
| Mismatch Strategy | `freeze_last` | Khi voice dài hơn video: freeze frame cuối |
| Transition | `none` | Hiệu ứng chuyển cảnh giữa segments |
| Segment Crop | `3.0%` | Crop nhẹ mỗi segment (anti-reup per segment) |
| Max Concurrent | `3` | Số task chạy song song (batch mode) |
| Max Retries | `3` | Số lần retry khi lỗi |
| Auto-retry | ✅ | Tự retry khi gặp lỗi tạm thời |
| Auto-populate timeline | ✅ | Sau pipeline xong → tự load clips vào timeline |

### Tab 4: 📁 Paths

| Setting | Giá trị | Mục đích |
|---------|---------|----------|
| Workspace | `E:\Aiagent\Projects\video-reup-studio-rebuild\workspace` | Thư mục chứa projects |
| Cookies | `cookies.txt` | File cookies cho yt-dlp (video restricted) |
| FFmpeg Bin | `ffmpeg_bin/` | Thư mục chứa ffmpeg.exe + ffprobe.exe |
| Image Output | (tùy) | Thư mục mặc định cho ảnh AI |
| Video Output | (tùy) | Thư mục mặc định cho video export |

### Tab 5: 🔧 Advanced

| Setting | Mục đích |
|---------|----------|
| Cache pipeline | Resume workflow nếu bị gián đoạn |
| Content sanitization | Tự xóa tên người nổi tiếng, nội dung nhạy cảm |
| Scene detection | Detect keyframes trước khi cắt (tránh cắt giữa chuyển cảnh) |
| Keep temp files | Giữ file tạm để debug |
| Log retention | Số ngày giữ log |

---

## Các trang chức năng

### 📥 Source — Tải video & 1-Click Auto

**Mục đích**: Nhập URL YouTube hoặc chọn file local → chạy toàn bộ pipeline tự động.

**Cách dùng**:
1. Paste YouTube URL vào ô input (hoặc bấm 📂 chọn file local)
2. Chọn Target Language (ngôn ngữ muốn dịch sang)
3. Chọn Platform (TikTok/YouTube/Facebook)
4. Chọn Voice Engine (OmniVoice hoặc Edge-TTS)
5. Tick/untick: Anti-Reup, Burn Subtitle, Split
6. Bấm "🚀 START AUTO PIPELINE"
7. Xem progress + log realtime
8. Pause/Cancel nếu cần

**Pipeline tự động chạy**:
```
Download → Transcribe → AI Rewrite → Voice per segment → Cut video → Compose → Anti-reup → Split → Export
```

---

### 📝 Script — Transcribe & Rewrite kịch bản

**Mục đích**: Xem/chỉnh sửa subtitle gốc và bản dịch AI.

**Cách dùng**:
1. Load SRT file (từ pipeline hoặc browse thủ công)
2. Xem bản gốc (trái) vs bản rewrite (phải)
3. Chọn target language → bấm "🤖 AI Rewrite"
4. Chỉnh sửa tay nếu cần
5. Bấm "💾 Save Rewritten" để lưu

**Khi nào dùng**: Khi muốn kiểm tra/chỉnh sửa kịch bản trước khi tạo voice.

---

### 🎙 Voice — Clone giọng & TTS

**Mục đích**: Tạo voice cho từng segment subtitle.

**Cách dùng**:
1. Chọn SRT file (bản đã rewrite)
2. Chọn Engine:
   - **OmniVoice**: Clone giọng (cần GPU CUDA)
     - Chọn Reference Audio (3s+ audio để clone giọng từ đó)
     - Nhập Instruct (style: "speak slowly", "excited", "whisper")
   - **Edge-TTS**: Free, nhanh, không cần GPU
     - Chọn voice từ danh sách
3. Chọn Language, Speed, Device
4. Bấm "🎙 Generate Voice Per Segment"
5. Mỗi segment SRT → 1 file WAV/MP3

**OmniVoice clone giọng**:
- Cần file audio 3 giây trở lên làm reference
- Tool sẽ clone giọng đó và đọc text bằng giọng clone
- Hỗ trợ 646 ngôn ngữ
- Cần NVIDIA GPU (CUDA)

---

### 🎬 Compose — Ghép video + voice + sub

**Mục đích**: Từ video gốc + voice segments + SRT → tạo video hoàn chỉnh.

**Cách dùng**:
1. Chọn Source Video (video gốc)
2. Chọn Rewritten SRT
3. Chọn Voice Segments folder
4. Chọn options:
   - Burn Subtitle (đốt sub vào video)
   - Transition (crossfade/fade black/none)
   - Mismatch strategy (khi voice dài/ngắn hơn video)
5. Bấm "🎬 COMPOSE VIDEO"

**Logic compose**:
- CẮT video gốc theo timestamps SRT (mỗi segment = 1 clip)
- Ghép voice vào đúng segment tương ứng
- Nếu voice dài hơn video → freeze frame cuối
- Nếu voice ngắn hơn → pad silence
- Burn subtitle lên video
- Concat tất cả segments → final video

---

### ⏱ Timeline — Chỉnh sửa trực quan

**Mục đích**: Editor trực quan để chỉnh tay trước khi export.

**3 tracks**:
- 🎬 Video: clips video/ảnh
- 🔊 Audio: voice segments
- 💬 Sub: subtitle entries

**Toolbar**:
- 🎬+ Video: thêm video file
- 🔊+ Audio: thêm audio file
- 💬+ Sub: thêm SRT (tự parse thành clips)
- 🖼+ Image: thêm ảnh (5s, Ken Burns effect khi export)
- ✂ Split: cắt clip tại playhead
- 🗑 Delete: xóa clip đang chọn
- ↩ Undo: hoàn tác
- Zoom: phóng to/thu nhỏ timeline

**Preview**: Xem video realtime, subtitle overlay, seek bar.

---

### 📤 Export — Xuất video final

**Mục đích**: Apply anti-reup + split + encode với thông số tùy chỉnh.

**Tab Platform**:
| Platform | Resolution | Max Duration |
|----------|-----------|--------------|
| TikTok | 1080x1920 (dọc) | 60s (tùy chỉnh) |
| YouTube | 1920x1080 (ngang) | 600s |
| Facebook | 1080x1080 (vuông) | 180s |

- Duration có thể chỉnh tay (10-3600s)
- FPS tùy chỉnh (0 = giữ nguyên)

**Tab Anti-Reup**:
| Thông số | Mô tả |
|----------|--------|
| Preset | light/medium/heavy |
| Crop % | Zoom vào 2-5% (thay đổi frame hash) |
| Speed | ±2-3% (không nhận ra bằng tai) |
| Hue shift | Dịch màu ±5° |
| KHÔNG flip | Spec-v2: không bao giờ lật video |
| Frame padding | Thêm 1-3 frame đen đầu/cuối |
| Metadata strip | Xóa tất cả EXIF, encoder info |

**Tab Encoding**:
| Thông số | Giá trị | Mô tả |
|----------|---------|--------|
| CRF | 15-35 (default 23) | Chất lượng (thấp = tốt hơn, file lớn hơn) |
| Video Bitrate | (optional) | Nếu set → dùng thay CRF |
| Audio Bitrate | 128k/192k/256k/320k | Chất lượng audio |
| Preset | ultrafast→veryslow | Tốc độ encode vs chất lượng |
| Codec | H.264 / H.265 | H.265 nhỏ hơn nhưng chậm hơn |

---

### 🧹 Watermark Remove

**Mục đích**: Xóa watermark (logo TikTok, Veo, etc.) khỏi video/ảnh.

**Cách dùng**:
1. Chọn file (image hoặc video)
2. Auto-detect (góc dưới phải) hoặc nhập tọa độ thủ công (X, Y, W, H)
3. Bấm "🧹 Remove Watermark"

**Engine**: LaMa inpainting (AI) → fallback simple fill nếu model chưa cài.

---

### 🔍 Upscale

**Mục đích**: Nâng độ phân giải video/ảnh.

**Cách dùng**:
1. Chọn file
2. Chọn target: 720p / 1080p / 1440p / 2160p
3. Bấm "🔍 Upscale"

**Engine**: Real-ESRGAN 4x-UltraSharp (GPU) → fallback FFmpeg lanczos.

---

### 🖼 BG Remove

**Mục đích**: Xóa nền ảnh (tạo thumbnail, isolate subject).

**Cách dùng**:
1. Chọn ảnh
2. Chọn background: Transparent / Green / Blue / White / Black
3. Bấm "🖼 Remove Background"

**Engine**: BiRefNet (rembg) — offline, không cần internet.

---

### 📐 Batch Resize

**Mục đích**: Resize hàng loạt ảnh cho các platform.

**Presets**:
- Instagram Post (1080x1080)
- Instagram Story (1080x1920)
- YouTube Thumbnail (1280x720)
- TikTok (1080x1920)
- Facebook Cover (820x312)
- Wallpaper HD/4K

**Modes**: Fit (crop center) / Pad (thêm viền) / Stretch

---

## Chức năng học từ NAVTools

| Chức năng | NAVTools | Video Reup Studio |
|-----------|----------|-------------------|
| Task Manager (multi-thread, cancel/pause) | ✅ QThread pool | ✅ Áp dụng |
| LLM Fallback Chain (multi-model) | ✅ Gemini chain | ✅ 9router chain |
| SQLite Settings (cached, thread-safe) | ✅ | ✅ Áp dụng |
| Browser Automation (Playwright) | ✅ Google Flow | 🔲 Chưa cần |
| Watermark Remove (LaMa) | ✅ | ✅ Áp dụng |
| Upscale (Real-ESRGAN) | ✅ | ✅ Áp dụng |
| BG Remove (BiRefNet) | ✅ | ✅ Áp dụng |
| TTS Vietnamese (VieNeu) | ✅ | ✅ Có sẵn (thêm bên cạnh OmniVoice) |
| Batch Resize (PIL presets) | ✅ | ✅ Áp dụng |
| YouTube → Scene → Prompt | ✅ | 🔲 Phase sau |
| Veo/Imagen API | ✅ | 🔲 Phase sau |
| Content Sanitization | ✅ | ✅ Setting có, chưa implement |
| Scene Detection | ✅ | ✅ Setting có, chưa implement |
| Dark Theme (QSS) | ✅ PySide6 | ✅ Áp dụng |
| Lazy Page Loading | ✅ | ✅ Pattern tương tự |

---

## Yêu cầu hệ thống

| Component | Yêu cầu |
|-----------|----------|
| Python | 3.11+ |
| PySide6 | 6.7+ |
| FFmpeg | Có trong ffmpeg_bin/ hoặc PATH |
| yt-dlp | pip install yt-dlp |
| Node.js | Cho yt-dlp YouTube extraction |
| edge-tts | pip install edge-tts |
| OmniVoice | pip install omnivoice (cần CUDA) |
| CUDA GPU | Cho OmniVoice + Whisper + ESRGAN |
| 9router | localhost:20128 (LLM API) |

---

## Quick Start

```bash
cd E:\Aiagent\Projects\video-reup-studio-rebuild\src
python main.py
```

1. Vào Settings → set API Endpoint, chọn Whisper model
2. Vào Source → paste YouTube URL → START
3. Chờ pipeline chạy xong
4. Vào Timeline xem kết quả
5. Vào Export → chỉnh params → Export

---

## File Structure per Project

```
workspace/
└── 2026-05-25_my-video/
    ├── source.mp4              ← video gốc
    ├── source.srt              ← sub gốc (download hoặc whisper)
    ├── rewritten.srt           ← AI rewrite (target language)
    ├── voice_segments/
    │   ├── seg_001.wav         ← voice segment 1
    │   ├── seg_002.wav
    │   └── ...
    ├── video_segments/         ← video gốc CẮT theo SRT
    │   ├── seg_001.mp4
    │   └── ...
    ├── output/
    │   ├── final_antireup.mp4
    │   ├── export_tiktok_001.mp4
    │   └── export_tiktok_002.mp4
    └── pipeline_summary.json
```
