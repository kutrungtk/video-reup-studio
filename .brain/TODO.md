# TODO — Cần fix/improve (session tiếp theo)

## Ưu tiên cao

### 1. Rewrite Sub — thêm giới hạn duration/từ
- Prompt rewrite phải có: "Viết lại nội dung này trong tối đa X giây (khoảng Y từ)"
- User set target duration trong Source page (không chỉ Settings)
- VD: video gốc 5 phút → rewrite thành 30s narration (75 từ)

### 2. ✅ Compose Page — Scene-based Timeline Editor (DONE)
- Scene-based (mỗi scene = 1 card: thumbnail + voice + subtitle + duration)
- Học từ NAVTools: scene-oriented, không phải generic video editor
- Load Project auto-detect (SRT → scenes, match voice + visuals theo index)
- Preview panel (video + image viewer, subtitle overlay)
- Right-click menu: replace visual, replace voice, edit subtitle, reorder, delete
- Compose from scenes → ComposeWorker (mode "scenes")
- Ken Burns cho image, trim+merge cho video, black+audio fallback
- Thumbnail hiện trực tiếp trên scene card

### 3. Compose — không bắt buộc video gốc
- Mode chính: ẢNH AI + voice + sub = video (news style)
- Mode phụ: video gốc cắt + voice (reup style)
- Mode kết hợp: mix ảnh AI + đoạn video gốc

### 4. OmniVoice — chưa test
- Cần test thực tế: `python -m omnivoice.cli.infer --text "..." --output out.wav`
- Kiểm tra OmniVoice đã cài chưa
- Fallback Edge-TTS phải hoạt động

## Ưu tiên trung bình

### 5. Storyboard → Visuals integration
- Storyboard output (VIDEO/IMAGE) phải tự động feed vào Visuals page
- Chỉ tạo ảnh cho scenes đánh dấu "IMAGE"
- Scenes "VIDEO" → cắt từ video gốc (nếu có) hoặc skip

### 6. Project flow liên tục
- Sau mỗi bước xong → tự động fill input cho bước tiếp theo
- VD: Source xong → Script tự load SRT
- Script xong → Voice tự load rewritten.srt
- Voice xong → Compose tự load voice_segments/

### 7. Google Gemini Flow — test tạo ảnh thực tế
- Login OK (cookies saved)
- Chưa test: gọi ImageFX API với cookies → tạo ảnh thực tế
- Cần verify endpoint + payload format

## Đã hoàn thành
- ✅ Download (yt-dlp + cookies + ffmpeg)
- ✅ Rewrite (LLM qua 9router, model từ Settings)
- ✅ Storyboard (AI phân loại VIDEO/IMAGE)
- ✅ Google Login (Chrome thật, cookies saved)
- ✅ Settings đầy đủ (LLM/Image/TTS/Pipeline/Paths)
- ✅ 9router image gen (format đúng)
- ✅ 16 visual effects
- ✅ All workers (QThread, cancel/pause)
- ✅ Dark theme, sidebar nav, 10 pages
