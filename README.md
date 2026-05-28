# 🎬 Video Reup Studio

Tool chỉnh sửa video hàng loạt — tải, edit lách bản quyền, xuất chuẩn HD cho TikTok/YouTube/Facebook/Instagram.

## ✨ Tính năng

- **📥 Batch Download** — Tải hàng loạt video từ YouTube/TikTok/Facebook (channel, playlist)
- **⚡ Quick Edit** — Anti-reup hàng loạt (xoay, crop, đổi tốc độ, hue, MD5), thêm logo/intro/outro/BGM
- **📤 Export** — Xuất video chuẩn HD/2K cho từng nền tảng, GPU acceleration
- **📸 Thumbnail Pro** — Tạo thumbnail từ frame video, thêm text với hiệu ứng pro
- **🔄 Batch Resize** — Resize ảnh/video hàng loạt
- **🎯 Watermark Remove** — Xóa watermark bằng AI inpainting
- **📐 Upscale** — Nâng độ phân giải video

## 🚀 Cài đặt (Windows)

### Bước 1: Cài Python

Tải Python 3.10+ từ [python.org](https://www.python.org/downloads/)

> ⚠️ Khi cài, **tick chọn "Add Python to PATH"**

Kiểm tra:
```
python --version
```

### Bước 2: Tải source code

```
git clone https://github.com/kutrungtk/video-reup-studio.git
cd video-reup-studio
```

Hoặc tải ZIP từ GitHub → giải nén.

### Bước 3: Cài thư viện

```
pip install -r requirements.txt
```

Danh sách thư viện:
| Thư viện | Chức năng |
|----------|-----------|
| PySide6 | Giao diện (GUI) |
| yt-dlp | Download video |
| edge-tts | Text-to-Speech (free) |
| deep-translator | Dịch ngôn ngữ |
| Pillow | Xử lý ảnh |
| requests | HTTP requests |

### Bước 3b (Tùy chọn): Cài OmniVoice — Clone giọng nói

> ⚠️ Yêu cầu: NVIDIA GPU + CUDA 11.8+

```
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install omnivoice
```

OmniVoice cho phép clone giọng nói từ 3 giây audio mẫu. Nếu không có GPU, app tự fallback sang Edge-TTS (free, không cần GPU).

👉 **Hướng dẫn chi tiết:** [docs/OMNIVOICE.md](docs/OMNIVOICE.md)

### Bước 4: Tải FFmpeg (BẮT BUỘC)

> ⚠️ **Không có FFmpeg = app không chạy được.** Đây là engine xử lý video.

Tải ffmpeg từ [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) → bản **ffmpeg-release-full.7z**

Giải nén, copy **cả 3 file** vào folder `ffmpeg_bin/` trong project:

```
video-reup-studio/
├── ffmpeg_bin/
│   ├── ffmpeg.exe     ← BẮT BUỘC
│   ├── ffprobe.exe    ← BẮT BUỘC (đọc thông tin video)
│   └── ffplay.exe     ← tùy chọn (preview)
├── src/
├── scripts/
└── ...
```

**Cách khác:** Cài ffmpeg vào PATH hệ thống:
1. Tải từ link trên
2. Giải nén vào `C:\ffmpeg\`
3. Thêm `C:\ffmpeg\bin` vào System PATH (Environment Variables)
4. Mở CMD mới → `ffmpeg -version` → thấy version = OK

### Bước 5: Chạy app

```
python src/main.py
```

## 📋 Hướng dẫn sử dụng

### 📥 Tải video hàng loạt
1. Vào **📥 Batch Download**
2. Paste URL kênh YouTube / playlist / TikTok
3. Chọn Resolution (1080p, 720p, 4K...)
4. Chọn folder lưu → **SCAN** → tick chọn video → **DOWNLOAD**

> 💡 YouTube public không cần cookie. TikTok/Facebook/Instagram có thể cần — xem [docs/COOKIES.md](docs/COOKIES.md)

### ⚡ Edit lách bản quyền (Quick Edit)
1. Vào **⚡ Quick Edit**
2. Chọn folder video hoặc chọn files
3. Tick/untick từng video muốn edit
4. Chỉnh slider Anti-Reup:
   - **Rotation:** 1-3° (xoay nhẹ, mắt không thấy)
   - **Speed:** 98-102% (đổi tốc độ nhẹ)
   - **Crop:** 1-3px (cắt viền, đổi resolution)
   - **Hue:** 2-5 (đổi màu nhẹ)
5. Tick **MD5 Change** (đổi metadata)
6. Thêm Logo / Intro / Outro / BGM nếu cần
7. **Chọn Export Format:**
   - Platform: TikTok / YouTube Shorts / YouTube / FB Reels / FB Feed / IG Reels
   - Chất lượng: Full HD 1080p / 2K 1440p
8. Bấm **START PROCESSING**

### 📤 Export Format — Thông số tự động

Khi chọn Platform + Chất lượng, tool tự tính:

| Platform | Full HD | 2K |
|----------|---------|-----|
| TikTok / YT Shorts / FB Reels / IG Reels | 1080×1920 (9:16) | 1440×2560 (9:16) |
| YouTube / FB Feed | 1920×1080 (16:9) | 2560×1440 (16:9) |

Encode params (tự động):
- **CRF 18** — chất lượng max, mắt không phân biệt được với gốc
- **maxrate 20M** (Full HD) / **30M** (2K) — đủ cho cảnh chuyển động nhanh
- **H.264 High Profile** — chuẩn mọi platform
- **30fps** — chuẩn TikTok/FB/IG
- **AAC stereo** — 192k (TikTok/FB/IG) hoặc 384k (YouTube)
- **faststart** — upload nhanh

### 🖥️ GPU Acceleration (Tự động)

Tool tự detect GPU và dùng hardware encoder:
- 🟢 **NVIDIA NVENC** — render nhanh 3-5x (GTX 1060+)
- 🔴 **AMD AMF** — render nhanh 3-4x (RX 5000+)
- 🔵 **Intel QSV** — render nhanh 2-3x (Intel Gen 7+)
- 💻 **CPU** — fallback nếu không có GPU

Không cần cấu hình gì — app tự detect khi khởi động.

### 📝 Lấy tiêu đề video
Copy file `scripts/extract_titles.py` vào folder chứa video đã edit, double-click chạy → ra file `titles.txt` (tự bỏ ngày tháng, giữ tiêu đề + hashtag).

### ⚙️ Cấu hình Settings

Vào **Settings** (biểu tượng ⚙️ trên sidebar) để cấu hình:

**Tab Voice / TTS:**
| Mục | Giải thích |
|-----|-----------|
| Default Engine | OmniVoice (clone giọng, cần GPU) hoặc Edge-TTS (free) |
| OmniVoice URL | URL server OmniVoice (mặc định localhost:8100) |
| Default Voice | Giọng Edge-TTS mặc định (VD: vi-VN-NamMinhNeural) |
| Voice Speed | Tốc độ đọc: +10% nhanh hơn, -5% chậm hơn |

**Tab Pipeline:**
| Mục | Giải thích |
|-----|-----------|
| Platform | Nền tảng xuất video (TikTok, YouTube, FB, IG) |
| Anti-Reup Preset | Mức anti-reup mặc định (Light/Medium/Heavy) |

**Tab Paths:**
| Mục | Giải thích |
|-----|-----------|
| Download folder | Folder mặc định lưu video tải về |
| Output folder | Folder mặc định lưu video đã edit |
| FFmpeg path | Đường dẫn ffmpeg.exe (tự detect nếu để trống) |

**Tab LLM / AI:**
| Mục | Giải thích |
|-----|-----------|
| LLM Provider | API cho AI rewrite script (9router, OpenAI, Gemini) |
| API Key | Key của provider đã chọn |
| Model | Model AI (VD: gpt-4o, gemini-pro) |

**Tab Advanced:**
| Mục | Giải thích |
|-----|-----------|
| Whisper Model | Model transcribe (large-v3 tốt nhất, medium nhanh hơn) |
| Device | cuda (GPU) hoặc cpu |
| Max threads | Số luồng xử lý song song |

## 📦 Yêu cầu hệ thống

| Yêu cầu | Tối thiểu | Khuyến nghị |
|----------|-----------|-------------|
| OS | Windows 10 | Windows 11 |
| Python | 3.10+ | 3.11+ |
| RAM | 4GB | 8GB+ |
| GPU | Không bắt buộc | NVIDIA GTX 1060+ |
| Ổ cứng | 500MB (app) | SSD (render nhanh hơn) |
| FFmpeg | Bắt buộc | Đã hướng dẫn ở trên |

## 🛠 Tech Stack

- **GUI:** PySide6 (Qt6)
- **Download:** yt-dlp (YouTube, TikTok, Facebook, Instagram, 1000+ sites)
- **Encode:** FFmpeg (H.264, AAC, GPU acceleration)
- **Image:** Pillow
- **TTS:** edge-tts
- **Translate:** deep-translator

## 📝 License

MIT
