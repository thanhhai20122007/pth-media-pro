---
title: PTH Media Pro
emoji: 🚀
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# 🚀 PTH MEDIA PRO - HỆ THỐNG TẢI & XỬ LÝ VIDEO ĐA NỀN TẢNG THÔNG MINH KHÔNG LOGO

Hệ thống tải, biên tập, lách bản quyền video tự động đa nền tảng mạnh mẽ nhất, tích hợp giao diện Web hiện đại, cửa sổ ứng dụng Desktop và chế độ Auto Reup tự động đăng bài đa kênh (TikTok, Facebook Reels, Threads).

---

## ✨ 1. Tính Năng Nổi Bật

### 🎬 Tải Video Đa Nền Tảng Không Logo (Watermark-Free)
- **TikTok & Douyin**: Tự động trích xuất trực tiếp stream video gốc HD **100% không dính logo watermark** và không dính ID người dùng.
- **TikTok Slideshow / Photo Album**: Tự động tải trọn bộ album ảnh chất lượng gốc kèm nhạc nền MP3.
- **Facebook**: Tải Reels, Watch, Video bài viết ở độ phân giải cao nhất (1080p Full HD / 720p HD).
- **YouTube**: Tải YouTube Shorts, Video dài, danh sách phát; hỗ trợ tải trực tiếp hoặc chuyển đổi MP3 320kbps.
- **Instagram**: Tải Reels, Video bài viết, Carousel không logo.
- **Threads, Twitter (X), Kuaishou, Pinterest, CapCut, Bilibili...**: Hỗ trợ toàn diện hơn 1000+ website.

### 📋 Giám Sát Clipboard Thông Minh (Smart Clipboard Sniffer)
- Chỉ cần bật tính năng giám sát và lướt web trên máy tính/điện thoại: Khi bạn bấm **Copy Link (Sao chép liên kết)** của bất kỳ video nào, Tool sẽ tự động bắt link ngay lập tức, phân tích và đưa vào hàng đợi tải về mà bạn không cần mở tool ra dán.

### ⚡ Bộ Lọc Hậu Kỳ Lách Bản Quyền FFmpeg Pro
- **Chuẩn hóa tỷ lệ dọc 9:16 (1080x1920)**: Tích hợp hiệu ứng **Blurred Background (Nền mờ nghệ thuật)** chuyên nghiệp hoặc viền đen cân đối.
- **Biến đổi mã băm hình ảnh (Visual Hash)**: Zoom nhẹ 2% và crop ma trận điểm ảnh để vượt qua các thuật toán quét quét trùng lặp.
- **Lệch sóng âm (Audio Fingerprint)**: Tăng tốc độ phát 1.02x (giữ giọng nói tự nhiên, không bị méo tiếng) kèm cân bằng tần số.
- **Xóa 100% Metadata**: Xóa bỏ hoàn toàn thông tin thiết bị quay, ngày giờ, chữ ký số của nền tảng cũ (`-map_metadata -1`).
- **Đóng dấu thương hiệu (Branding Watermark)**: Tự động chèn logo PNG trong suốt của bạn vào góc video.

### 🖥 Giao Diện Người Dùng Hiện Đại (Web Dashboard & Desktop App)
- Chạy giao diện Web mượt mà (FastAPI + WebSocket real-time) với Dark Mode sang trọng phong cách Studio.
- Hiển thị tiến trình tải (%), tốc độ tải (MB/s), dung lượng, thumbnail xem trước.
- **Trình phát video tích hợp (Built-in Player)**: Xem trước video đã tải ngay trên giao diện.
- **Nút "Mở thư mục" 1 chạm**: Mở ngay vị trí tệp video trong Windows Explorer.
- **Chế độ tải hàng loạt (Batch Download)**: Dán danh sách hàng trăm link để tool tự động cày ngầm.

### 🤖 Tự Động Reup Đa Kênh (Playwright Auto-Post)
- Hỗ trợ tự động phân phối bài đăng lên TikTok Studio, Facebook Reels và Threads từ mã nguồn gốc `auto_reup_pro.py`.

---

## 📁 2. Cấu Trúc Thư Mục Dự Án

```plaintext
TOOL Tải video đa năng/
├── KHOI_DONG_TOOL.bat      # Menu khởi động trung tâm tiện lợi
├── run_web.bat             # Chạy giao diện Web Dashboard trên trình duyệt
├── run_gui.bat             # Chạy giao diện Cửa Sổ Desktop App độc lập
├── main.py                 # Điểm khởi chạy chính đa năng
├── auto_reup_pro.py        # Tệp mã nguồn Auto Reup đa kênh & CLI
├── requirements.txt        # Danh sách thư viện Python
├── bin/
│   ├── ffmpeg.exe          # Đã tích hợp sẵn, không lo thiếu môi trường
│   └── ffprobe.exe
├── core/
│   ├── config.py           # Cấu hình tập trung, nhận diện đường dẫn
│   ├── database.py         # Cơ sở dữ liệu SQLite (tasks.db) quản lý hàng đợi
│   ├── downloader.py       # Lõi trích xuất đa nền tảng không logo
│   ├── processor.py        # Lõi FFmpeg render chống trùng lặp & tách MP3
│   ├── clipboard_watcher.py# Lõi giám sát clipboard ngầm
│   └── reup_engine.py      # Lõi tự động đăng bài qua Playwright
├── web/
│   ├── app.py              # Server FastAPI & WebSocket
│   ├── templates/
│   │   └── index.html      # Giao diện Web Dashboard hiện đại
│   └── static/             # CSS & JavaScript
├── downloads/
│   ├── videos/             # Video gốc đã tải không logo
│   ├── audios/             # Tệp âm thanh MP3 trích xuất
│   └── processed/          # Video đã qua xử lý lách bản quyền 9:16
├── assets/
│   └── logo.png            # File logo đóng dấu bản quyền riêng
└── profiles/
    └── browser_data/       # Nơi lưu phiên đăng nhập TikTok, FB, Threads
```

---

## 🚀 3. Hướng Dẫn Sử Dụng Nhanh

### Cách 1: Sử dụng Menu 1-Click (Khuyên dùng)
- Click đúp vào tệp **`KHOI_DONG_TOOL.bat`**.
- Chọn:
  - **Phím 1**: Mở Giao diện Web trên trình duyệt Chrome/Edge (`http://127.0.0.1:5000`).
  - **Phím 2**: Mở Giao diện Cửa Sổ Desktop App.
  - **Phím 3**: Chạy Auto Reup đăng bài tự động.
  - **Phím 4**: Đăng nhập lưu tài khoản mạng xã hội.
  - **Phím 5**: Xem tiến độ các video trên Terminal.
  - **Phím 6**: Mở thư mục chứa video đã tải.

### Cách 2: Chạy Bằng Lệnh Dòng Lệnh (Terminal / PowerShell)

1. **Khởi chạy giao diện Web:**
   ```bash
   python main.py --mode web
   ```

2. **Khởi chạy cửa sổ Desktop App:**
   ```bash
   python main.py --mode gui
   ```

3. **Chạy Auto Reup tự động đăng bài:**
   ```bash
   python auto_reup_pro.py
   ```

4. **Đăng nhập lưu tài khoản TikTok, FB, Threads:**
   ```bash
   python auto_reup_pro.py --login
   ```

5. **Xem danh sách tiến độ video:**
   ```bash
   python main.py --status
   # hoặc:
   python auto_reup_pro.py --status
   ```

---

## ⚙ 4. Tùy Chỉnh Chuyên Sâu

1. **Thay đổi logo đóng dấu:**
   - Thay thế file ảnh `assets/logo.png` bằng ảnh logo PNG nền trong suốt của bạn.
2. **Thay đổi bộ hashtag tự động khi đăng bài:**
   - Mở giao diện Web -> Nhấn biểu tượng Bánh răng (Cài đặt) -> Nhập chuỗi hashtag mong muốn.
3. **Bật / Tắt chế độ lách bản quyền tự động:**
   - Trên thanh tải video, bạn có thể chọn chế độ:
     - *Video Sạch (Không Logo)*: Giữ nguyên chất lượng và tỉ lệ gốc.
     - *Tách Nhạc MP3 320k*: Chỉ lấy âm thanh chất lượng cao.
     - *Lách Bản Quyền 9:16 (FFmpeg)*: Tự động chạy bộ lọc chống quét trùng lặp.
