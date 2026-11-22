import os
import re
import sys
import time
import json
import subprocess
import urllib.parse
import requests
from typing import Dict, Any, Optional, Callable

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from core.config import (
    BIN_DIR,
    VIDEOS_DIR,
    AUDIOS_DIR,
    PROCESSED_DIR,
    RAW_DIR,
    FFMPEG_EXE,
    BROWSER_DATA_DIR,
    COOKIE_FILE,
)


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """Loại bỏ ký tự không hợp lệ trong tên tệp Windows"""
    if not filename:
        return "video"
    clean = re.sub(r'[\\/*?:"<>|]', "", filename)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:max_length] if clean else "video"


def resolve_redirect_url(url: str) -> str:
    """Mở rộng link rút gọn (fb.watch, facebook.com/share, threads.com/share, pin.it) về link gốc"""
    u = url.strip()

    # KHÔNG can thiệp vào link TikTok / Douyin và Facebook Story
    # Tránh bị bot-detector chặn redirect về https://www.tiktok.com/?_r=1 hoặc login.php
    if any(k in u.lower() for k in ("tiktok.com", "douyin.com", "facebook.com/stories", "fb.com/stories")):
        return u

    # Tự động phân giải link Facebook share (/share/r/, /share/v/, /share/p/, fb.watch)
    if any(k in u for k in ("fb.watch", "facebook.com/share", "fb.com/share")):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            }
            resp = requests.get(u, headers=headers, allow_redirects=True, timeout=8)
            final_url = resp.url
            if final_url and "login" not in final_url and any(k in final_url for k in ("reel", "watch", "videos", "posts")):
                return final_url
            
            # Quét tìm canonical hoặc og:url trong HTML
            html = resp.text
            canonical = re.findall(r'rel="canonical"\s+href="([^"]+)"', html, re.I)
            if canonical and "login" not in canonical[0]:
                return canonical[0]
            og = re.findall(r'property="og:url"\s+content="([^"]+)"', html, re.I)
            if og and "login" not in og[0]:
                return og[0]

            # Quét ID reel/video trong HTML
            reel_match = re.search(r'facebook\.com/(?:reel|watch/\?v=)(\d+)', html)
            if reel_match:
                return f"https://www.facebook.com/reel/{reel_match.group(1)}/"
        except Exception:
            pass
        return u

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        }
        resp = requests.head(u, headers=headers, allow_redirects=True, timeout=8)
        if resp.url and resp.url.startswith("http") and "login" not in resp.url and "checkpoint" not in resp.url:
            from urllib.parse import urlparse
            p = urlparse(resp.url)
            if p.path and p.path not in ("/", "") and "_r=1" not in resp.url:
                return resp.url
    except Exception:
        pass
    return u


def detect_platform(url: str) -> str:
    """Nhận diện nền tảng chính xác từ URL"""
    u = url.lower()
    if any(k in u for k in ("tiktok.com", "vt.tiktok.com", "vm.tiktok.com")):
        return "tiktok"
    if any(k in u for k in ("douyin.com", "iesdouyin.com")):
        return "douyin"
    if any(k in u for k in ("youtube.com", "youtu.be")):
        return "youtube"
    if any(k in u for k in ("facebook.com", "fb.watch", "fb.com")):
        return "facebook"
    if "instagram.com" in u:
        return "instagram"
    if any(k in u for k in ("threads.net", "threads.com")):
        return "threads"
    if any(k in u for k in ("twitter.com", "x.com")):
        return "twitter"
    if any(k in u for k in ("kuaishou.com", "kwai.com")):
        return "kuaishou"
    if any(k in u for k in ("pinterest.com", "pin.it")):
        return "pinterest"
    if any(k in u for k in ("xiaohongshu.com", "xhslink.com")):
        return "xiaohongshu"
    if "bilibili.com" in u:
        return "bilibili"
    if "capcut.com" in u:
        return "capcut"
    return "general"


# Session dùng chung với Connection Pooling để tái sử dụng TCP handshake và tăng tối đa tốc độ tải
_SESSION = None

def get_session():
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=30,
            pool_maxsize=50,
            max_retries=3,
        )
        _SESSION.mount("https://", adapter)
        _SESSION.mount("http://", adapter)
    return _SESSION


def download_file_stream(
    url: str,
    output_path: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> bool:
    """Tải tệp theo stream HTTP tối ưu bộ đệm lớn (512KB) và tính toán tiến trình thực tế"""
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/",
    }
    if headers:
        req_headers.update(headers)

    session = get_session()
    resp = session.get(url, headers=req_headers, stream=True, timeout=35)
    resp.raise_for_status()

    total_size = int(resp.headers.get("content-length", 0))
    downloaded = 0
    start_time = time.time()
    last_update = 0

    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=512 * 1024):
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)

            now = time.time()
            if now - last_update > 0.3:
                last_update = now
                elapsed = max(now - start_time, 0.001)
                speed_bytes = downloaded / elapsed
                speed_str = f"{speed_bytes / (1024 * 1024):.1f} MB/s"
                pct = (downloaded / total_size * 100) if total_size > 0 else 50.0
                if progress_callback:
                    progress_callback(min(pct, 99.0), speed_str)

    if progress_callback:
        progress_callback(100.0, "Hoàn tất")
    return True


def extract_with_playwright_browser(
    url: str,
    task_id: int,
    format_type: str = "video",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    ENGINE DỰ PHÒNG: Dùng Playwright với Cookie phiên đăng nhập thật của người dùng
    để bóc tách video từ các trang bị Meta hoặc Cloudflare chặn (Threads, Instagram, Facebook Private)
    """
    if sync_playwright is None:
        raise Exception("Playwright chưa được cài đặt trên môi trường này.")

    print(f"[PlaywrightEngine] Đang khởi chạy trình duyệt bóc tách: {url}")
    if progress_callback:
        progress_callback(10.0, "Mở trình duyệt...")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA_DIR,
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
        )
        page = context.pages[0] if context.pages else context.new_page()

        captured_media = []

        def handle_response(res):
            try:
                ct = res.headers.get("content-type", "")
                r_url = res.url
                if ("video/mp4" in ct or ".mp4" in r_url or "bytevc1" in r_url) and "blob:" not in r_url:
                    captured_media.append(r_url)
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(4000)

            title = page.title() or "Video Mạng Xã Hội"
            title = re.sub(r"\s+", " ", title).strip()

            # 1. Tìm trong thẻ meta
            meta_video = None
            for sel in ('meta[property="og:video"]', 'meta[property="og:video:secure_url"]', 'meta[name="twitter:player:stream"]'):
                if page.locator(sel).count() > 0:
                    meta_video = page.locator(sel).first.get_attribute("content")
                    if meta_video and meta_video.startswith("http"):
                        break

            # 2. Tìm trong thẻ video DOM
            dom_video = None
            if page.locator("video").count() > 0:
                dom_video = page.locator("video").first.get_attribute("src")

            best_url = meta_video or dom_video or (captured_media[0] if captured_media else None)

            if not best_url:
                # Kiểm tra nếu bị kẹt ở trang đăng nhập
                if "login" in page.url.lower():
                    raise Exception("Trang này yêu cầu đăng nhập! Hãy chọn 'Đăng nhập tài khoản' trên Menu để lưu phiên.")
                raise Exception("Không tìm thấy luồng phát video trên trang này.")

            clean_name = sanitize_filename(title)
            out_file = os.path.join(VIDEOS_DIR, f"{clean_name}_{task_id}.mp4")

            if progress_callback:
                progress_callback(30.0, "Đang tải stream...")

            download_file_stream(best_url, out_file, progress_callback)
            file_size = os.path.getsize(out_file) if os.path.exists(out_file) else 0

            return {
                "title": title,
                "author": "Social Media",
                "thumbnail": "",
                "duration": 0,
                "file_path": out_file,
                "file_size": file_size,
                "platform": detect_platform(url),
            }

        finally:
            context.close()


def download_with_ytdlp_engine(
    url: str,
    task_id: int,
    platform: str,
    format_type: str = "video",
    quality: str = "1080p",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    ENGINE CHÍNH: yt-dlp tối tân với Chrome Impersonation (curl_cffi)
    Hỗ trợ TikTok 100% không logo, YouTube 4K, Facebook Reels HD
    """
    out_dir = AUDIOS_DIR if format_type == "audio" else VIDEOS_DIR
    out_template = os.path.join(out_dir, f"video_{task_id}_%(title).70s.%(ext)s")

    last_pct = 0.0

    def ytdl_hook(d):
        nonlocal last_pct
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            speed = d.get("speed", 0) or 0
            speed_str = f"{speed / (1024 * 1024):.1f} MB/s" if speed else "Đang tải..."
            pct = (downloaded / total * 100) if total > 0 else last_pct
            last_pct = min(pct, 99.0)
            if progress_callback:
                progress_callback(last_pct, speed_str)
        elif d["status"] == "finished":
            if progress_callback:
                progress_callback(99.5, "Hoàn tất xuất file...")

    # Cấu hình đa luồng tải mảnh video (HLS/DASH) siêu tốc
    ydl_opts = {
        "outtmpl": out_template,
        "ffmpeg_location": BIN_DIR,
        "progress_hooks": [ytdl_hook],
        "no_playlist": True,
        "quiet": True,
        "no_warnings": True,
        "concurrent_fragment_downloads": 16, # Tăng tốc 16 luồng song song đặc trị video dài/livestream/podcast
        "buffersize": 16 * 1024 * 1024,      # Bộ đệm 16MB giảm tối đa độ trễ I/O đĩa
        "http_chunk_size": 10485760,         # 10MB chunk tối ưu truyền tải
        "retries": 15,
        "fragment_retries": 15,
        "continuedl": True,
        "nocheckcertificate": True,          # Bỏ qua xác thực SSL lặp lại trên từng mảnh phân đoạn
        "socket_timeout": 30,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb"], # Khắc phục triệt để YouTube throttling trên video dài
                "player_skip": ["configs", "webpage"]
            }
        },
        "postprocessor_args": {
            "Merger": ["-c", "copy"]         # Ghép luồng video + audio bằng stream copy chỉ 1-2 giây
        }
    }

    # Chỉ sử dụng aria2c nếu file nhị phân thực sự tồn tại trong hệ thống (tránh lỗi trên Linux/Render)
    import shutil
    aria2_exe = os.path.join(BIN_DIR, "aria2c.exe") if sys.platform == "win32" else "aria2c"
    has_aria2 = (sys.platform == "win32" and os.path.exists(aria2_exe)) or (sys.platform != "win32" and shutil.which("aria2c") is not None)
    if has_aria2 and platform not in ("tiktok", "douyin", "youtube"):
        ydl_opts["external_downloader"] = {"default": aria2_exe}
        ydl_opts["external_downloader_args"] = {
            "default": [
                "-s", "16",
                "-x", "16",
                "-k", "1M",
                "--min-split-size=1M",
                "--max-connection-per-server=16",
                "--file-allocation=none",
                "--summary-interval=0"
            ]
        }

    # Bật Chrome Impersonation qua curl_cffi để vượt qua Cloudflare/Bot-detection
    try:
        ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
    except Exception:
        pass

    if format_type == "audio" or quality == "audio":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                },
                {"key": "FFmpegMetadata"},
            ],
        })
    else:
        # Cấu hình chất lượng linh hoạt: 720p (siêu tốc cho 4G), 1080p (Full HD), 4k (gốc cao nhất)
        if quality == "720p":
            if platform == "tiktok":
                ydl_opts["format"] = "bestvideo[height<=720][format_note!=watermarked]+bestaudio/best[height<=720][format_note!=watermarked]/best[height<=720]/best"
            elif platform == "youtube":
                ydl_opts["format"] = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best"
            elif platform == "facebook":
                ydl_opts["format"] = "best[height<=720]/bestvideo[height<=720]+bestaudio/best"
            else:
                ydl_opts["format"] = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best"
        elif quality in ("4k", "2k", "best"):
            if platform == "tiktok":
                ydl_opts["format"] = "bestvideo[format_note!=watermarked]+bestaudio/best[format_note!=watermarked]/best"
            elif platform == "youtube":
                ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            else:
                ydl_opts["format"] = "bestvideo+bestaudio/best"
        else:
            # Mặc định 1080p Full HD
            if platform == "tiktok":
                ydl_opts["format"] = "bestvideo[format_note!=watermarked]+bestaudio/best[format_note!=watermarked]/best"
            elif platform == "youtube":
                ydl_opts["format"] = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
            elif platform == "facebook":
                ydl_opts["format"] = "best[height<=1080]/bestvideo[height<=1080]+bestaudio/best"
            else:
                ydl_opts["format"] = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best"
        ydl_opts["merge_output_format"] = "mp4"

    # Kiểm tra nếu có cookie file trong data/cookies.txt
    if os.path.exists(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 10:
        ydl_opts["cookiefile"] = COOKIE_FILE

    info = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as first_err:
        print(f"[SmartDownloader] Tải lần 1 gặp lỗi ({str(first_err)[:100]}). Kích hoạt cơ chế tải dự phòng siêu tốc...")
        # Loại bỏ external_downloader và hạ cấp sang định dạng tương thích cao nhất
        ydl_opts.pop("external_downloader", None)
        ydl_opts.pop("external_downloader_args", None)
        if quality == "720p":
            ydl_opts["format"] = "best[height<=720]/best"
        elif quality in ("4k", "2k", "best"):
            ydl_opts["format"] = "best"
        else:
            ydl_opts["format"] = "best[height<=1080]/best[height<=720]/best"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

    if not info:
        raise Exception("Không thể trích xuất thông tin video.")

    raw_title = info.get("title", "")
    author = info.get("uploader") or info.get("channel") or info.get("creator") or "User"
    thumbnail = info.get("thumbnail", "")
    duration = info.get("duration", 0)

    target_file = None
    if "requested_downloads" in info and info["requested_downloads"]:
        target_file = info["requested_downloads"][0].get("filepath")
    if not target_file or not os.path.exists(target_file):
        target_file = ydl.prepare_filename(info)
        if format_type == "audio":
            target_file = os.path.splitext(target_file)[0] + ".mp3"

    # Tìm lại file nếu tên tệp chuẩn hóa khác đuôi
    if not target_file or not os.path.exists(target_file):
        for fname in os.listdir(out_dir):
            if f"video_{task_id}_" in fname or f"audio_{task_id}_" in fname:
                target_file = os.path.join(out_dir, fname)
                break

    file_size = os.path.getsize(target_file) if target_file and os.path.exists(target_file) else 0

    if progress_callback:
        progress_callback(100.0, "Hoàn tất")

    return {
        "title": raw_title,
        "author": author,
        "thumbnail": thumbnail,
        "duration": duration,
        "file_path": target_file,
        "file_size": file_size,
        "platform": platform,
    }


def download_threads_engine(
    url: str,
    task_id: int,
    format_type: str = "video",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    ENGINE CHUYÊN BIỆT CHO THREADS (threads.net & threads.com / share):
    Giải quyết triệt để lỗi 'HTTP Error 429: Too Many Requests' do máy chủ Meta chặn IP mạng,
    bóc tách trực tiếp luồng stream CDN Instagram MP4 gốc sạch không logo.
    """
    print(f"[ThreadsEngine] Bắt đầu giải mã bài viết Threads: {url}")
    if progress_callback:
        progress_callback(10.0, "Đang kết nối luồng CDN Threads...")

    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "x-respond-with": "html",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    }

    try:
        resp = requests.get(jina_url, headers=headers, timeout=25)
    except Exception as net_err:
        raise Exception(f"Không thể kết nối đến máy chủ giải mã Threads: {net_err}")

    if resp.status_code != 200:
        raise Exception(f"Không thể đọc nội dung bài viết Threads (HTTP {resp.status_code})")

    html = resp.text.replace(r'\/', '/')

    # 1. Bóc tách tiêu đề bài viết
    m_title = re.search(r'<title>(.*?)</title>', html, re.DOTALL)
    raw_title = m_title.group(1).replace("on Threads", "").strip() if m_title else "Threads Video"
    raw_title = re.sub(r'\s+', ' ', raw_title).strip()
    if not raw_title or len(raw_title) < 2:
        raw_title = f"Threads_Video_{task_id}"

    # 2. Bóc tách ảnh thumbnail
    m_thumb = re.search(r'property="og:image"\s+content="([^"]+)"', html)
    thumbnail = m_thumb.group(1).replace('&amp;', '&') if m_thumb else ""

    # 3. Bóc tách luồng video MP4 từ Instagram/Meta CDN
    matches = re.findall(r'https://[a-zA-Z0-9.-]+\.cdninstagram\.com/[^"\'\s<>]+\.mp4[^"\'\s<>]*', html)
    valid_videos = []
    for m in matches:
        if "static.cdninstagram.com" not in m and "rsrc.php" not in m:
            clean_m = m.replace('&amp;', '&').replace('\\u0026', '&')
            if clean_m not in valid_videos:
                valid_videos.append(clean_m)

    if not valid_videos:
        # Dự phòng: quét toàn bộ liên kết có đuôi mp4
        gen_matches = re.findall(r'https://[^"\'\s<>]+\.mp4[^"\'\s<>]*', html)
        for m in gen_matches:
            if "static." not in m and "rsrc.php" not in m:
                clean_m = m.replace('&amp;', '&').replace('\\u0026', '&')
                if clean_m not in valid_videos:
                    valid_videos.append(clean_m)

    if not valid_videos:
        raise Exception("Không tìm thấy video trong bài viết Threads này (bài viết chỉ chứa văn bản hoặc hình ảnh).")

    best_video_url = valid_videos[0]
    clean_name = sanitize_filename(raw_title, max_length=60)

    if progress_callback:
        progress_callback(25.0, "Đang tải video gốc từ CDN...")

    if format_type == "audio":
        temp_video = os.path.join(VIDEOS_DIR, f"temp_th_{task_id}.mp4")
        out_file = os.path.join(AUDIOS_DIR, f"audio_{task_id}_{clean_name}.mp3")
        try:
            download_file_stream(best_video_url, temp_video, progress_callback)
            if progress_callback:
                progress_callback(90.0, "Đang trích xuất MP3 320k...")
            cmd = [
                FFMPEG_EXE, "-y",
                "-i", temp_video,
                "-vn", "-ab", "320k",
                "-ar", "44100",
                out_file
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            file_size = os.path.getsize(out_file) if os.path.exists(out_file) else 0
        finally:
            if os.path.exists(temp_video):
                try:
                    os.remove(temp_video)
                except Exception:
                    pass
    else:
        out_file = os.path.join(VIDEOS_DIR, f"video_{task_id}_{clean_name}.mp4")
        download_file_stream(best_video_url, out_file, progress_callback)
        file_size = os.path.getsize(out_file) if os.path.exists(out_file) else 0

    return {
        "title": raw_title,
        "author": "Threads Creator",
        "thumbnail": thumbnail,
        "duration": 0,
        "file_path": out_file,
        "file_size": file_size,
        "platform": "threads",
    }


def parse_fb_story_id(url: str):
    """Bóc tách User/Page ID và Story Media ID từ URL Story Facebook"""
    import base64
    match = re.search(r'facebook\.com/stories/(\d+)/([^/?]+)', url)
    if not match:
        return None, None
    user_id = match.group(1)
    b64_part = match.group(2)
    media_id = None
    try:
        padded = b64_part + '=' * (-len(b64_part) % 4)
        decoded = base64.b64decode(padded).decode('utf-8', errors='ignore')
        nums = re.findall(r'\d{10,25}', decoded)
        if nums:
            media_id = nums[-1]
    except Exception:
        pass
    return user_id, media_id


def download_facebook_story_engine(
    url: str,
    task_id: int,
    format_type: str = "video",
    quality: str = "1080p",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    ENGINE CHUYÊN BIỆT CHO FACEBOOK STORIES:
    Bóc tách và tải story Facebook cá nhân và Fanpage.
    Bảo mật Meta yêu cầu đăng nhập tài khoản (cookies) để trích xuất tin 24h.
    """
    print(f"[FacebookStoryEngine] Khởi động giải mã Story: {url}")
    if progress_callback:
        progress_callback(10.0, "Đang phân tích Story Facebook...")

    has_cookies = os.path.exists(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 10
    if not has_cookies:
        raise Exception("Story Facebook luôn yêu cầu quyền xem. Vui lòng vào Cài đặt (⚙️) ở góc trên và dán Cookie Facebook (c_user, xs...) để tải Story mượt mà!")

    user_id, media_id = parse_fb_story_id(url)

    # 1. Thử cào trực tiếp qua Session có gắn Cookies
    try:
        import http.cookiejar
        jar = http.cookiejar.MozillaCookieJar(COOKIE_FILE)
        jar.load(ignore_discard=True, ignore_expires=True)
        session = requests.Session()
        session.cookies = jar
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Ch-Ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        if progress_callback:
            progress_callback(25.0, "Đang kết nối Facebook Story với Cookie...")

        resp = session.get(url, headers=headers, allow_redirects=True, timeout=20)
        final_url = resp.url
        if "login" in final_url.lower():
            raise Exception("Cookie Facebook hiện tại không hợp lệ hoặc đã hết hạn đăng nhập. Vui lòng cập nhật Cookie mới trong Cài đặt (⚙️)!")

        html = resp.text

        # Quét tìm luồng video stream MP4 từ Meta CDN trong nội dung HTML/JSON
        video_urls = []
        hd_matches = re.findall(r'playable_url_quality_hd["\:\s]+(https?://[^"\s\\]+)', html)
        if not hd_matches:
            hd_matches = re.findall(r'browser_native_hd_url["\:\s]+(https?://[^"\s\\]+)', html)
        sd_matches = re.findall(r'playable_url["\:\s]+(https?://[^"\s\\]+)', html)
        if not sd_matches:
            sd_matches = re.findall(r'browser_native_sd_url["\:\s]+(https?://[^"\s\\]+)', html)

        if hd_matches:
            video_urls.extend(hd_matches)
        if sd_matches:
            video_urls.extend(sd_matches)

        # Quét dự phòng tất cả link video fbcdn.net
        if not video_urls:
            fbcdn_videos = re.findall(r'https?:[\\/]+[a-zA-Z0-9.-]+\.fbcdn\.net[\\/][^"\'\s<>]+\.mp4[^"\'\s<>]*', html)
            for fv in fbcdn_videos:
                clean_fv = fv.replace(r'\/', '/').replace('\\u0026', '&').replace('&amp;', '&')
                if clean_fv not in video_urls:
                    video_urls.append(clean_fv)

        if video_urls:
            target_stream = video_urls[0].replace(r'\/', '/').replace('\\u0026', '&').replace('&amp;', '&')
            if progress_callback:
                progress_callback(50.0, "Bắt đầu tải trực tiếp video Story...")

            # Bóc tách tiêu đề/tên người đăng
            title_match = re.search(r'<title>(.*?)</title>', html)
            raw_title = title_match.group(1).replace(" | Facebook", "").strip() if title_match else f"Story_{user_id or task_id}"
            clean_title = sanitize_filename(raw_title)

            out_dir = VIDEOS_DIR if format_type == "video" else AUDIOS_DIR
            out_file = os.path.join(out_dir, f"video_{task_id}_{clean_title[:30]}.mp4")

            v_resp = session.get(target_stream, stream=True, timeout=30)
            total_size = int(v_resp.headers.get('content-length', 0))
            downloaded = 0
            with open(out_file, "wb") as vf:
                for chunk in v_resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        vf.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and progress_callback:
                            pct = 50.0 + (downloaded / total_size * 48.0)
                            progress_callback(min(pct, 98.0), f"{downloaded / (1024*1024):.1f} MB")

            if format_type == "audio":
                audio_file = os.path.join(AUDIOS_DIR, f"audio_{task_id}_{clean_title[:30]}.mp3")
                cmd = [FFMPEG_EXE, "-y", "-i", out_file, "-vn", "-ab", "320k", audio_file]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(out_file):
                    try:
                        os.remove(out_file)
                    except Exception:
                        pass
                out_file = audio_file

            if progress_callback:
                progress_callback(100.0, "Hoàn tất")

            return {
                "title": raw_title,
                "author": f"User {user_id}" if user_id else "Facebook User",
                "thumbnail": "",
                "duration": 0,
                "file_path": out_file,
                "file_size": os.path.getsize(out_file) if os.path.exists(out_file) else 0,
                "platform": "facebook",
            }
    except Exception as scrape_err:
        print(f"[FacebookStoryEngine] Cào trực tiếp báo: {scrape_err}. Chuyển sang yt-dlp cookie engine...")

    # 2. TẦNG 2: Sử dụng yt-dlp với cookie file
    candidates = []
    if media_id:
        candidates.append(f"https://www.facebook.com/watch/?v={media_id}")
        if user_id:
            candidates.append(f"https://www.facebook.com/{user_id}/videos/{media_id}/")
            candidates.append(f"https://www.facebook.com/story.php?story_fbid={media_id}&id={user_id}")
    candidates.append(url)

    last_ytdl_err = None
    for cand in candidates:
        try:
            print(f"[FacebookStoryEngine] Thử yt-dlp với candidate: {cand}")
            return download_with_ytdlp_engine(
                url=cand,
                task_id=task_id,
                platform="facebook",
                format_type=format_type,
                quality=quality,
                progress_callback=progress_callback
            )
        except Exception as ey:
            last_ytdl_err = ey

    raise Exception("Không thể tải Story Facebook này. Cookie hiện tại có thể đã hết hạn hoặc Story được chia sẻ trong danh sách hạn chế/Bạn bè riêng tư.")


def download_video_smart(
    url: str,
    task_id: int,
    format_type: str = "video",
    quality: str = "1080p",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    HÀM ĐIỀU PHỐI THÔNG MINH ĐA TẦNG:
    - Nếu là Facebook Story: Kích hoạt ngay FacebookStoryEngine giải mã tin 24h bằng Cookie
    - Nếu là Threads: Kích hoạt ngay ThreadsEngine chuyên dụng vượt chặn HTTP 429 của Meta
    - Các nền tảng khác: Chạy yt-dlp với Chrome TLS Impersonation (curl_cffi)
    - Tầng dự phòng: Playwright Browser với cookie phiên đăng nhập thực tế (khi có cài đặt)
    """
    cleaned_url = url.strip()
    cleaned_url = resolve_redirect_url(cleaned_url)
    platform = detect_platform(cleaned_url)

    print(f"[SmartDownloader] Bắt đầu tải Task #{task_id} | Platform: {platform} | Quality: {quality} | URL: {cleaned_url}")

    # 1. NỀN TẢNG FACEBOOK STORY: Ưu tiên Engine chuyên dụng giải mã Story
    if platform == "facebook" and ("/stories/" in cleaned_url.lower() or "story.php" in cleaned_url.lower()):
        return download_facebook_story_engine(
            cleaned_url,
            task_id=task_id,
            format_type=format_type,
            quality=quality,
            progress_callback=progress_callback,
        )

    # 2. NỀN TẢNG THREADS: Ưu tiên Engine chuyên dụng vượt chặn HTTP 429
    if platform == "threads":
        try:
            return download_threads_engine(
                cleaned_url,
                task_id=task_id,
                format_type=format_type,
                progress_callback=progress_callback,
            )
        except Exception as th_err:
            print(f"[SmartDownloader] Threads Engine gặp lỗi: {th_err}. Chuyển sang Playwright dự phòng...")
            if sync_playwright is not None:
                try:
                    return extract_with_playwright_browser(
                        cleaned_url,
                        task_id=task_id,
                        format_type=format_type,
                        progress_callback=progress_callback,
                    )
                except Exception:
                    raise th_err
            raise th_err

    # 3. CÁC NỀN TẢNG KHÁC (TikTok, YouTube, Facebook, Instagram, X, Douyin): yt-dlp Chrome Impersonation
    try:
        return download_with_ytdlp_engine(
            cleaned_url,
            task_id=task_id,
            platform=platform,
            format_type=format_type,
            quality=quality,
            progress_callback=progress_callback,
        )
    except Exception as ytdl_err:
        err_str = str(ytdl_err)
        print(f"[SmartDownloader] yt-dlp gặp vấn đề: {err_str[:160]}")

        # 4. TẦNG DỰ PHÒNG: Playwright Browser Engine (Chỉ kích hoạt nếu Playwright thực sự được cài đặt)
        if sync_playwright is not None and (any(w in err_str.lower() for w in ("429", "login", "redirected", "rate-limit", "generic", "unsupported", "cannot parse", "no video", "extractor", "story", "stories")) or platform == "facebook"):
            print("[SmartDownloader] Kích hoạt Playwright Browser Engine để vượt rào cản...")
            try:
                return extract_with_playwright_browser(
                    cleaned_url,
                    task_id=task_id,
                    format_type=format_type,
                    progress_callback=progress_callback,
                )
            except Exception as browser_err:
                b_err = str(browser_err)
                if "login" in b_err.lower() or "429" in err_str:
                    raise Exception("Bài viết này yêu cầu tài khoản. Hãy mở Menu -> chọn [4] Đăng nhập tài khoản để lưu phiên!")
                raise Exception(f"Lỗi tải: {b_err[:150]}")

        # Thân thiện hóa thông báo lỗi thực tế cho người dùng mọi thiết bị
        has_cookies = os.path.exists(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 10
        if "/stories/" in cleaned_url.lower() or "story.php" in cleaned_url.lower():
            if not has_cookies:
                raise Exception("Story Facebook luôn yêu cầu quyền xem. Vui lòng vào Cài đặt (⚙️) ở góc trên và dán Cookie Facebook (c_user, xs...) để tải Story mượt mà!")
            else:
                raise Exception("Không thể xem Story này. Cookie Facebook có thể đã hết hạn hoặc bạn không nằm trong danh sách được xem Story.")
        elif "instagram.com/stories" in cleaned_url.lower():
            if not has_cookies:
                raise Exception("Story Instagram yêu cầu quyền xem. Vui lòng vào Cài đặt (⚙️) và dán Cookie Instagram để tải!")
            else:
                raise Exception("Không thể tải Story Instagram. Cookie đã hết hạn hoặc Story ở chế độ bạn bè thân thiết.")
        elif "login" in err_str.lower() or "private" in err_str.lower():
            raise Exception("Video này ở chế độ riêng tư hoặc yêu cầu đăng nhập tài khoản (vào Cài đặt ⚙️ để thêm Cookie).")
        elif "unavailable" in err_str.lower() or "not found" in err_str.lower() or "404" in err_str:
            raise Exception("Video không tồn tại hoặc đã bị chủ sở hữu xóa.")
        elif "unsupported" in err_str.lower():
            raise Exception("Đường dẫn video không được hỗ trợ hoặc không đúng định dạng.")
        else:
            clean_err = re.sub(r'ERROR:\s*\[[^\]]+\]\s*', '', err_str).strip()
            clean_err = clean_err.split("\n")[0]
            raise Exception(f"Lỗi tải: {clean_err[:120]}")


def extract_playlist_or_channel(url: str, max_items: int = 30) -> Dict[str, Any]:
    """
    BÓC TÁCH TOÀN BỘ KÊNH HOẶC PLAYLIST HÀNG LOẠT:
    - Bóc tách danh sách video từ Playlist YouTube, Kênh YouTube (@channel/videos), Kênh TikTok (@user), Douyin...
    - Trả về tiêu đề, số lượng và danh sách link video để đưa vào hàng đợi tải đa luồng song song
    """
    cleaned_url = url.strip()
    cleaned_url = resolve_redirect_url(cleaned_url)

    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "playlistend": max_items,
        "socket_timeout": 30,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "player_skip": ["configs", "webpage"]
            }
        }
    }

    try:
        ydl_opts["impersonate"] = ImpersonateTarget.from_str("chrome")
    except Exception:
        pass

    cookie_file = os.path.join(os.path.dirname(RAW_DIR), "cookies.txt")
    if os.path.exists(cookie_file):
        ydl_opts["cookiefile"] = cookie_file

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(cleaned_url, download=False)
        if not info:
            raise Exception("Không thể lấy danh sách video từ liên kết này")

        entries = info.get("entries")
        playlist_title = info.get("title") or "Danh sách video"
        uploader = info.get("uploader") or info.get("channel") or ""

        videos = []
        if entries is not None:
            for item in list(entries)[:max_items]:
                if not item:
                    continue
                v_url = item.get("url") or item.get("webpage_url")
                if not v_url and item.get("id"):
                    v_url = f"https://www.youtube.com/watch?v={item['id']}"
                elif v_url and not v_url.startswith("http"):
                    v_url = f"https://www.youtube.com/watch?v={v_url}"

                if v_url:
                    v_title = item.get("title") or "Video"
                    v_thumb = item.get("thumbnail") or ""
                    v_duration = item.get("duration") or 0
                    videos.append({
                        "url": v_url,
                        "title": v_title,
                        "thumbnail": v_thumb,
                        "duration": v_duration
                    })
        else:
            # Liên kết chỉ là 1 video đơn lẻ
            videos.append({
                "url": cleaned_url,
                "title": playlist_title,
                "thumbnail": info.get("thumbnail") or "",
                "duration": info.get("duration") or 0
            })

        return {
            "title": playlist_title,
            "uploader": uploader,
            "count": len(videos),
            "videos": videos
        }

