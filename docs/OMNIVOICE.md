# 🎙 Hướng dẫn cài đặt OmniVoice

OmniVoice là engine clone giọng nói chất lượng cao, hỗ trợ 646 ngôn ngữ. Chỉ cần 3 giây audio mẫu để clone giọng bất kỳ.

## Yêu cầu hệ thống

| Yêu cầu | Tối thiểu | Khuyến nghị |
|----------|-----------|-------------|
| GPU | NVIDIA GTX 1060 (6GB VRAM) | RTX 3060+ (8GB+ VRAM) |
| CUDA | 11.8+ | 12.1+ |
| RAM | 8GB | 16GB |
| Python | 3.10+ | 3.11 |
| OS | Windows 10/11 | Windows 11 |

> ⚠️ **Không có NVIDIA GPU?** App tự fallback sang Edge-TTS (free, không cần GPU, chất lượng thấp hơn).

## Bước 1: Cài CUDA Toolkit

1. Kiểm tra GPU: mở CMD → `nvidia-smi`
2. Tải CUDA Toolkit: https://developer.nvidia.com/cuda-downloads
3. Chọn: Windows → x86_64 → 11/10 → exe (local)
4. Cài đặt (chọn Express)
5. Kiểm tra: `nvcc --version`

## Bước 2: Cài PyTorch với CUDA

```
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

Kiểm tra CUDA hoạt động:
```python
python -c "import torch; print(torch.cuda.is_available())"
# Output: True
```

## Bước 3: Cài OmniVoice

```
pip install omnivoice
```

Lần đầu chạy sẽ tự download model (~2GB).

## Bước 4: Test thử

```
python -m omnivoice.cli.infer --text "Xin chào, đây là giọng clone" --output test.wav --language vi --device cuda
```

Nếu ra file `test.wav` → cài thành công.

## Bước 5: Clone giọng (Voice Cloning)

Chuẩn bị file audio mẫu:
- **Thời lượng:** 3-10 giây (tối ưu 5-7s)
- **Chất lượng:** Rõ ràng, không nhiễu, 1 người nói
- **Format:** WAV hoặc MP3, 16kHz+ mono

Test clone:
```
python -m omnivoice.cli.infer --text "Nội dung cần đọc" --ref_audio "mau_giong.wav" --language vi --device cuda --output output.wav
```

## Cấu hình trong Video Reup Studio

Vào **Settings → Voice / TTS**:

| Mục | Giá trị | Giải thích |
|-----|---------|-----------|
| Default Engine | `OmniVoice (CUDA — high quality)` | Engine chính |
| OmniVoice URL | `http://localhost:8100/tts` | Nếu dùng server mode (tùy chọn) |
| Default Voice (Edge-TTS) | `vi-VN-NamMinhNeural` | Fallback khi không có GPU |
| Voice Speed | `+0%` | Tốc độ đọc (VD: `+10%` nhanh hơn, `-5%` chậm hơn) |

## Sử dụng trong app

1. Vào **🎙 Voice** page
2. Chọn Engine: **OmniVoice (CUDA clone)**
3. Chọn Language: Vietnamese (hoặc ngôn ngữ khác)
4. Browse **Ref Audio**: chọn file giọng mẫu 3-10s
5. (Tùy chọn) Nhập Instruct: "giọng MC tin tức, rõ ràng"
6. Bấm **Generate Voice**

## Server Mode (Tùy chọn — cho máy yếu)

Nếu muốn chạy OmniVoice trên máy khác (server GPU):

```
# Trên máy server (có GPU):
python -m omnivoice.server --host 0.0.0.0 --port 8100

# Trong app Settings → OmniVoice URL:
http://192.168.1.xxx:8100/tts
```

## Troubleshoot

| Lỗi | Nguyên nhân | Cách fix |
|-----|-------------|----------|
| `CUDA not available` | Chưa cài CUDA hoặc PyTorch CPU | Cài lại PyTorch với CUDA (Bước 2) |
| `Out of memory` | VRAM không đủ | Giảm batch size hoặc dùng model nhỏ hơn |
| `Model not found` | Chưa download model | Chạy lần đầu sẽ tự tải, cần internet |
| `Audio too short` | Ref audio < 3s | Dùng audio mẫu dài hơn (5-7s tối ưu) |
| `Permission denied` | Antivirus block | Thêm folder vào whitelist Windows Defender |

## Không có GPU? Dùng Edge-TTS

Edge-TTS miễn phí, không cần GPU, chất lượng tốt (giọng Microsoft):

Trong Settings → Default Engine → chọn **Edge-TTS (Free)**

Giọng Việt Nam hay:
- `vi-VN-NamMinhNeural` (nam)
- `vi-VN-HoaiMyNeural` (nữ)

Giọng tiếng Anh:
- `en-US-GuyNeural` (nam)
- `en-US-JennyNeural` (nữ)
