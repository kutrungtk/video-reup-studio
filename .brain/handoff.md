# Handoff — video-reup-studio-rebuild

> **Last updated:** 2026-05-28 14:46 +07
> **From session:** `20260528_113826_91b0c2` (1593 messages, 3.49 MB state — quá tải)
> **Reason:** long-session — session quá dài, stream interrupt liên tiếp

## 🎯 Current State

Project ở giai đoạn **Phase B+ (Components đã ổn, đang mở rộng platform support)**.

- Core 14 pages đã hoàn thành: Source, Script, Voice, Visuals, Compose, Export, BatchDownload, Watermark, Upscale, BgRemove, BatchResize, Thumbnail, Settings, Project.
- Smart encode (Platform × Quality) — DONE.
- TikTok download — DONE (mobile API + retry + smart audio merge).
- Đang viết: **Douyin downloader** (port ABogus signing từ Galaxy-Douyin-Ultimate-Studio).
- Đang đọc dở: `src/downloaders/douyin_lib/abogus.py` (đến line 612/865).

## 📁 Active Files

| File | Status | Note |
|------|--------|------|
| `src/downloaders/douyin_lib/abogus.py` | 🔧 đang đọc | line 612-661 dở dang, cần đọc tiếp tới 865 để hiểu ABogus constructor |
| `src/ui/pages/batch_download_page.py` | ✅ TikTok done | Mobile API + retry 3x + smart 2-pass audio merge |
| `src/main.py` | ✅ stable | UTF-8 force OK |

## 🐛 In-progress Issues

- [ ] **Douyin downloader chưa wire**: đã commit support skeleton (`71f972c`) nhưng cần ABogus signing để bypass Douyin web challenge
  - Hypothesis: port ABogus class từ Galaxy-Douyin → tạo signature cho API request
  - Last attempt: đang đọc `abogus.py` để hiểu constructor params

- [ ] **TikTok batch download nguyên kênh chậm**: retry 3 lần × delay 3s × N videos = rất chậm
  - Đã thử: yt-dlp nightly (`d0f1b34`) — fix ổn hơn nhưng vẫn cần retry
  - Pending: test nguyên kênh có rate limit không

- [ ] **Facebook/Instagram download**: chưa test trong app

- [ ] **Individual checkbox click**: user báo lỗi click checkbox riêng lẻ trong BatchDownload — chưa fix

## 📌 Decisions Made (chưa kịp ghi vào decisions.md)

Append các quyết định sau vào `decisions.md`:

- **`_edited` suffix CHỈ cho Quick Edit/Export**, KHÔNG cho download. Download dùng `YYYY-MM-DD_TiêuĐề.ext`.
- **curl_cffi 0.10.0** (không phải 0.15.0) — compatible với yt-dlp impersonation.
- **TikTok Mobile API** (`api_hostname=api22-normal-c-alisg.tiktokv.com`) — bypass JS challenge ổn định hơn web.
- **TikTok scan**: `ignoreerrors=True` + `extract_flat` (bắt buộc cho TikTok).
- **TikTok download**: `quiet=True` + `ignoreerrors=True` (combo duy nhất không crash).
- **TikTok formats lie about audio**: tất cả 11 formats báo `acodec=aac` nhưng thực tế video-only → cần ffprobe check + 2-pass merge.
- **yt-dlp nightly** dùng cho TikTok extractor (stable hơn release).
- **Douyin xử lý riêng** (không dùng yt-dlp), port ABogus signing.

## ➡️ Next Step

1. **Đọc tiếp `abogus.py`** từ line 662 → 865 để nắm trọn ABogus class constructor.
2. **Port ABogus** sang `src/downloaders/douyin_lib/` của project.
3. **Wire Douyin downloader** vào BatchDownload page (detect URL douyin.com → dùng Douyin engine thay TikTok).
4. **Test** với 1 video Douyin thật để confirm signing work.

## 🚀 Quick Start

```bash
cd /mnt/e/Aiagent/Projects/video-reup-studio-rebuild

# Verify state
git status
git log --oneline -10

# Push pending commits
git push

# Test app launch
python src/main.py

# Đọc tiếp abogus.py
# (file: src/downloaders/douyin_lib/abogus.py, từ line 662)
```

## ⚠️ DO NOT

- **KHÔNG** dùng yt-dlp cho Douyin — nó đã thử và Douyin block mạnh hơn TikTok. Phải dùng API trực tiếp + ABogus.
- **KHÔNG** đổi `_edited` naming convention — user explicitly muốn giữ `YYYY-MM-DD_Title.ext` (download) và `YYYY-MM-DD_Title_edited.ext` (export).
- **KHÔNG** dùng curl_cffi 0.15.0 — incompatible với yt-dlp impersonation. Chốt 0.10.0.
- **KHÔNG** giả định TikTok formats có audio dù acodec=aac — phải ffprobe check thực tế.
- **KHÔNG** edit `constants.py` mà không cập nhật `get_encode_params()` cùng lúc.
- **KHÔNG** dùng `subprocess.run()` cho ffmpeg trong main thread — phải QProcess hoặc QThread (đã code QThread sẵn).
- **KHÔNG** đổi smart encode dropdowns Platform × Quality — user đã chốt 2 options là đủ.

## 🔗 Related Context

- `.brain/spec.md` — full project spec
- `.brain/tasks.md` — task breakdown
- `.brain/TODO.md` — TODO list user-managed
- `README.md` — overview với install + run instructions
- `docs/COOKIES.md` — Cookie guide
- GitHub: https://github.com/kutrungtk/video-reup-studio
- TikTok test URL: `https://vt.tiktok.com/ZSxVGNKSF/`
- Reference: https://github.com/JonathanNguyen1985/Galaxy-Douyin-Ultimate-Studio-2026

## 🤝 Resume Protocol

Khi mở session mới:

1. ✅ Đọc file này (`handoff.md`) trước
2. ✅ Đọc `spec.md` + `tasks.md` + `TODO.md`
3. ✅ Đọc `decisions.md`
4. ✅ Confirm với user: "Đã đọc handoff. Đang dở Douyin downloader (đọc `abogus.py` line 612). Tiếp tục đọc đến 865 và port ABogus class?"
5. ✅ Sau user OK → resume từ Next Step #1
6. ✅ Append 8 decisions trong section "Decisions Made" vào `decisions.md`
7. ✅ Archive handoff cũ:
   ```bash
   mkdir -p .brain/handoff-archive
   mv .brain/handoff.md .brain/handoff-archive/2026-05-28-1446.md
   ```
