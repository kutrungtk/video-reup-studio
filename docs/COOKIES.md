# 🍪 Hướng dẫn Cookie cho Download Video

## Khi nào cần Cookie?

| Nền tảng | Video công khai | Video riêng tư |
|----------|----------------|----------------|
| **YouTube** | ❌ Không cần | ✅ Cần (age-restricted, members-only) |
| **TikTok** | ⚠️ Đôi khi cần (2025+) | ✅ Cần |
| **Douyin** | ✅ Luôn cần | ✅ Cần |
| **Facebook** | ⚠️ Giúp tải HD, bypass login wall | ✅ Cần (group, private) |
| **Instagram** | ✅ Gần như luôn cần (2025+) | ✅ Cần |

> 💡 **YouTube video công khai**: tải bình thường, KHÔNG cần cookie.

---

## Cách Export Cookie

### Cách 1: Tự động từ trình duyệt (Khuyến nghị)

App hỗ trợ `--cookies-from-browser` — tự lấy cookie từ trình duyệt đang đăng nhập.

Trong **Settings → Paths**, chọn Browser:
- `firefox` (khuyến nghị — ít lỗi nhất)
- `chrome`
- `edge`
- `brave`

> ⚠️ **Chrome trên Windows (2025+)**: Google thêm "App-Bound Encryption" khiến việc đọc cookie khó hơn. Nếu lỗi, dùng **Firefox** thay thế.

### Cách 2: Export file cookie thủ công

1. Cài extension trình duyệt:
   - **Firefox**: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)
   - **Chrome/Edge**: [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)

2. Đăng nhập vào nền tảng (TikTok, Facebook, Instagram...)

3. Click extension → **Export** → lưu file `cookies.txt`

4. Copy file vào project:
   ```
   video-reup-studio/
   ├── cookies-tiktok.txt
   ├── cookies-facebook.txt
   ├── cookies-instagram.txt
   └── cookies-douyin.txt
   ```

5. Trong app **Settings → Paths** → chọn file cookie tương ứng

### Format file cookie (Netscape):
```
# Netscape HTTP Cookie File
.tiktok.com	TRUE	/	FALSE	0	sessionid	abc123xyz...
.tiktok.com	TRUE	/	TRUE	0	tt_webid	789456...
```

---

## Hướng dẫn theo từng nền tảng

### 🎵 TikTok

**Thường cần cookie** (2025+ TikTok block IP nhiều hơn). Nếu gặp lỗi "Your IP address is blocked":

1. Đăng nhập TikTok trên Firefox
2. Trong app Settings → Browser: `firefox`
3. Hoặc export cookie file → chọn trong Settings
4. Nếu vẫn lỗi → cần proxy/VPN (TikTok block IP theo vùng)

**URL hỗ trợ:**
```
https://www.tiktok.com/@username/video/7123456789012345678
https://vm.tiktok.com/ZMxxxxxxx/
https://www.tiktok.com/t/ZTxxxxxxx/
```

### 🎵 Douyin (TikTok Trung Quốc)

**Luôn cần cookie** + có thể cần IP Trung Quốc (VPN).

1. Mở trình duyệt → vào douyin.com → đăng nhập
2. Export cookie → lưu `cookies-douyin.txt`
3. Trong app chọn file cookie

**URL hỗ trợ:**
```
https://www.douyin.com/video/7123456789012345678
https://v.douyin.com/iRxxxxxx/
```

> ⚠️ Douyin hay thay đổi API — giữ yt-dlp luôn mới nhất: `pip install -U yt-dlp`

### 📘 Facebook

**Video công khai** thường tải được không cần cookie. Cookie giúp:
- Tải chất lượng HD (không cookie → SD)
- Bypass "đăng nhập để xem"
- Tải video từ group kín

1. Đăng nhập Facebook trên Firefox
2. Settings → Browser: `firefox`

**URL hỗ trợ:**
```
https://www.facebook.com/watch/?v=1234567890
https://www.facebook.com/username/videos/1234567890/
https://www.facebook.com/reel/1234567890
https://fb.watch/xxxxxxx/
```

### 📷 Instagram

**Gần như luôn cần cookie** (2025+). Instagram chặn rất mạnh.

1. Đăng nhập Instagram trên Firefox
2. Settings → Browser: `firefox`
3. Hoặc export cookie file

**URL hỗ trợ:**
```
https://www.instagram.com/reel/ABCdefGHI/
https://www.instagram.com/p/ABCdefGHI/
https://www.instagram.com/stories/username/
```

> ⚠️ **Không dùng tài khoản chính** để tải hàng loạt — Instagram có thể khóa tạm. Tạo tài khoản phụ.

### ▶️ YouTube

**Không cần cookie** cho video công khai. Chỉ cần khi:
- Video 18+ (age-restricted)
- Video members-only
- Video private (được share link)

Nếu gặp lỗi "Sign in to confirm you're not a bot":
1. Settings → Browser: `firefox`
2. Hoặc thử: cập nhật yt-dlp (`pip install -U yt-dlp`)

---

## Troubleshoot

| Lỗi | Nguyên nhân | Cách fix |
|-----|-------------|----------|
| `403 Forbidden` | Cần cookie hoặc cookie hết hạn | Export cookie mới |
| `Login required` | Nền tảng yêu cầu đăng nhập | Thêm cookie |
| `Unable to extract cookies from chrome` | Chrome App-Bound Encryption | Dùng Firefox thay |
| `Video unavailable` | Geo-restricted hoặc bị xóa | Thử VPN hoặc kiểm tra URL |
| `HTTP Error 429` | Rate limit (tải quá nhiều) | Chờ 5-10 phút, thêm `--sleep-interval 3` |
| Cookie hết hạn | Session cookie mất khi đóng browser | Export lại, dùng "Remember me" khi login |

## Mẹo quan trọng

1. **Cập nhật yt-dlp thường xuyên**: `pip install -U yt-dlp` — các extractor hay bị hỏng
2. **Dùng Firefox** cho cookie — ít lỗi hơn Chrome trên Windows
3. **Không dùng tài khoản chính** cho tải hàng loạt
4. **Cookie hết hạn** — export lại mỗi 1-2 tuần
5. **Thêm delay** khi tải nhiều: app đã có sleep giữa các video
