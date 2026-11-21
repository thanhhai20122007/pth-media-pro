import os
import re
import sys
import time
import json
import random
import sqlite3
import argparse
import threading
import subprocess
import requests
import pyperclip
from playwright.sync_api import sync_playwright

# ==================== 1. CẤU HÌNH TÙY CHỈNH ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "bin")

# Đảm bảo ffmpeg trong bin/ được ưu tiên trong PATH
if os.path.exists(BIN_DIR) and BIN_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")

FFMPEG_EXE = os.path.join(BIN_DIR, "ffmpeg.exe") if os.path.exists(os.path.join(BIN_DIR, "ffmpeg.exe")) else "ffmpeg"

DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
VIDEOS_DIR = os.path.join(DOWNLOADS_DIR, "videos")
AUDIOS_DIR = os.path.join(DOWNLOADS_DIR, "audios")

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
PROFILE_DIR = os.path.join(BASE_DIR, "profiles", "browser_data")
DB_PATH = os.path.join(DATA_DIR, "tasks.db")

# Đặt file logo.png vào thư mục assets/ nếu muốn tự động đóng dấu góc trên bên phải
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

# Bật True để kích hoạt bộ lọc lách quét trùng lặp (zoom 2% + tốc độ 1.02x + xóa metadata)
ENABLE_ANTI_DUPLICATE = True

# Bộ hashtag riêng sẽ tự động gắn vào cuối mỗi bài đăng
CUSTOM_HASHTAGS = "#xuhuong #viral #reels #shorts"

# Thời gian nghỉ giữa các lần đăng bài (giây) để bảo vệ tài khoản khỏi checkpoint
UPLOAD_DELAY_SECONDS = 600  # 10 phút

# Bật / Tắt từng nền tảng muốn tự động đăng
ENABLE_TIKTOK = True
ENABLE_FACEBOOK_REELS = True
ENABLE_THREADS = True

SUPPORTED_DOMAINS = (
    "youtube.com", "youtu.be", "tiktok.com", "douyin.com",
    "facebook.com", "fb.watch", "threads.net", "instagram.com", "x.com", "twitter.com"
)

for folder in (RAW_DIR, PROCESSED_DIR, VIDEOS_DIR, AUDIOS_DIR, ASSETS_DIR, PROFILE_DIR):
    os.makedirs(folder, exist_ok=True)


# ==================== 2. QUẢN LÝ DATABASE (SQLITE) ====================
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    return conn


def claim_task():
    """Khóa nguyên tử một tác vụ để nhiều worker tải song song không bị trùng lặp"""
    with get_db() as conn:
        cur = conn.execute("""
            UPDATE tasks
            SET status = 'DOWNLOADING', updated_at = CURRENT_TIMESTAMP
            WHERE id = (
                SELECT id FROM tasks WHERE status = 'PENDING' AND retry_count < 3 ORDER BY id ASC LIMIT 1
            )
            RETURNING *;
        """)
        row = cur.fetchone()
        return dict(row) if row else None


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                platform TEXT DEFAULT 'general',
                title TEXT,
                author TEXT,
                thumbnail TEXT,
                raw_path TEXT,
                final_path TEXT,
                file_size INTEGER DEFAULT 0,
                duration INTEGER DEFAULT 0,
                status TEXT DEFAULT 'PENDING',
                progress REAL DEFAULT 0.0,
                speed TEXT DEFAULT '',
                format_type TEXT DEFAULT 'video',
                retry_count INTEGER DEFAULT 0,
                error_log TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def clean_caption(raw_title: str) -> str:
    """Loại bỏ hashtag cũ và khoảng trắng thừa, ghép hashtag của bạn."""
    cleaned = re.sub(r"#\S+", "", raw_title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "Khoảnh khắc thú vị mỗi ngày"
    return f"{cleaned[:120]} {CUSTOM_HASHTAGS}".strip()


# ==================== 3. WORKER 1: BẮT LINK CLIPBOARD ====================
def clipboard_watcher():
    last_text = ""
    while True:
        try:
            text = pyperclip.paste().strip()
            if text and text != last_text and text.startswith("http"):
                last_text = text
                if any(domain in text.lower() for domain in SUPPORTED_DOMAINS):
                    with get_db() as conn:
                        cur = conn.execute(
                            "INSERT OR IGNORE INTO tasks (url, status) VALUES (?, 'PENDING')",
                            (text,)
                        )
                        if cur.rowcount > 0:
                            print(f"\n[Clipboard] + Đã nạp link mới: {text}")
        except Exception:
            pass
        time.sleep(1)


# ==================== 4. WORKER 2: TẢI VIDEO SẠCH KHÔNG LOGO ====================
def download_stream(url: str, output_path: str):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36"}
    resp = requests.get(url, headers=headers, stream=True, timeout=30)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=128 * 1024):
            if chunk:
                f.write(chunk)


def download_worker(worker_id: int = 1):
    while True:
        task = claim_task()
        if not task:
            time.sleep(1)
            continue

        task_id, url = task["id"], task["url"]
        print(f"[Downloader #{worker_id}] Đang tải ID #{task_id} từ {url[:50]}...")

        clean_downloaded = False
        clean_title = ""
        expected_file = os.path.join(RAW_DIR, f"video_{task_id}.mp4")

        # 1. Nếu là TikTok / Douyin, ưu tiên lấy trực tiếp link sạch không logo qua API TikWM
        if any(d in url.lower() for d in ("tiktok.com", "douyin.com")):
            try:
                api_res = requests.get("https://www.tikwm.com/api/", params={"url": url, "hd": 1}, timeout=15).json()
                if api_res.get("code") == 0 and api_res.get("data"):
                    v_data = api_res["data"]
                    clean_title = clean_caption(v_data.get("title", ""))
                    play_url = v_data.get("hdplay") or v_data.get("play")
                    if play_url:
                        if play_url.startswith("/"):
                            play_url = "https://www.tikwm.com" + play_url
                        download_stream(play_url, expected_file)
                        clean_downloaded = True
                        print(f"[TikTok Clean] Tải thành công video không logo cho ID #{task_id}!")
            except Exception as e:
                print(f"[Downloader] Lỗi Clean API: {e}, chuyển sang yt-dlp...")

        # 2. Nếu là Threads, lấy trực tiếp stream sạch từ Instagram/Meta CDN (bỏ qua triệt để HTTP 429)
        if not clean_downloaded and any(d in url.lower() for d in ("threads.net", "threads.com")):
            try:
                jina_url = f"https://r.jina.ai/{url}"
                j_res = requests.get(jina_url, headers={"x-respond-with": "html"}, timeout=25)
                if j_res.status_code == 200:
                    html_clean = j_res.text.replace(r'\/', '/')
                    m_title = re.search(r'<title>(.*?)</title>', html_clean, re.DOTALL)
                    raw_th_title = m_title.group(1).replace("on Threads", "") if m_title else "Threads Video"
                    clean_title = clean_caption(raw_th_title)
                    v_matches = re.findall(r'https://[a-zA-Z0-9.-]+\.cdninstagram\.com/[^"\'\s<>]+\.mp4[^"\'\s<>]*', html_clean)
                    valid_v = [m.replace('&amp;', '&').replace('\\u0026', '&') for m in v_matches if "static." not in m and "rsrc.php" not in m]
                    if valid_v:
                        download_stream(valid_v[0], expected_file)
                        clean_downloaded = True
                        print(f"[Threads Clean] Tải thành công video CDN Threads cho ID #{task_id}!")
            except Exception as th_e:
                print(f"[Downloader] Threads Clean gặp lỗi: {th_e}, thử yt-dlp...")

        # 3. Sử dụng lõi yt-dlp cho các nền tảng khác hoặc khi fallback
        if not clean_downloaded:
            try:
                raw_template = os.path.join(RAW_DIR, f"video_{task_id}.%(ext)s")
                cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--ffmpeg-location", BIN_DIR,
                    "--impersonate", "chrome",
                    "--no-playlist",
                    "--concurrent-fragments", "8",
                    "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
                    "--merge-output-format", "mp4",
                    "--print-json",
                    "-o", raw_template,
                    url
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                json_lines = [line for line in result.stdout.strip().splitlines() if line.startswith("{")]
                info = json.loads(json_lines[-1]) if json_lines else {}

                clean_title = clean_caption(info.get("title", ""))
                downloaded_file = info.get("_filename") if os.path.exists(info.get("_filename", "")) else expected_file
                if os.path.exists(downloaded_file) and downloaded_file != expected_file:
                    os.rename(downloaded_file, expected_file)
                clean_downloaded = True

            except Exception as e:
                err_msg = str(e)[:200]
                print(f"[Downloader] Lỗi tải ID #{task_id}: {err_msg}")
                with get_db() as conn:
                    conn.execute("""
                        UPDATE tasks
                        SET retry_count = retry_count + 1,
                            error_log = ?,
                            status = CASE WHEN retry_count >= 2 THEN 'FAILED' ELSE 'PENDING' END
                        WHERE id = ?
                    """, (err_msg, task_id))
                time.sleep(5)
                continue

        if clean_downloaded and os.path.exists(expected_file):
            with get_db() as conn:
                conn.execute(
                    "UPDATE tasks SET status = 'PROCESSING', title = ?, raw_path = ?, progress = 50.0 WHERE id = ?",
                    (clean_title or f"Video #{task_id}", expected_file, task_id)
                )
            print(f"[Downloader] Tải xong ID #{task_id}: {clean_title[:45]}")


# ==================== 5. WORKER 3: HẬU KỲ VIDEO (FFMPEG) ====================
def process_worker():
    while True:
        with get_db() as conn:
            task = conn.execute(
                "SELECT * FROM tasks WHERE status = 'PROCESSING' ORDER BY id ASC LIMIT 1"
            ).fetchone()

        if not task:
            time.sleep(2)
            continue

        task_id, raw_path = task["id"], task["raw_path"]
        final_path = os.path.join(PROCESSED_DIR, f"ready_{task_id}.mp4")
        print(f"[FFmpeg] Đang render hậu kỳ lách bản quyền ID #{task_id}...")

        try:
            # Chuẩn hóa khung hình dọc 1080x1920 với nền mờ nghệ thuật
            vf_chain = (
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5[bg];"
                "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2[merged];"
                "[merged]scale=1102:1958,crop=1080:1920,setpts=0.98*PTS[v_out]"
            )
            af_chain = "atempo=1.02"

            if os.path.exists(LOGO_PATH):
                cmd = [
                    FFMPEG_EXE, "-y", "-i", raw_path, "-i", LOGO_PATH,
                    "-filter_complex", f"{vf_chain};[1:v]scale=160:-1[wm];[v_out][wm]overlay=W-w-40:40",
                    "-af", af_chain,
                    "-map_metadata", "-1",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    final_path
                ]
            else:
                cmd = [
                    FFMPEG_EXE, "-y", "-i", raw_path,
                    "-filter_complex", vf_chain,
                    "-map", "[v_out]",
                    "-map", "0:a?",
                    "-af", af_chain,
                    "-map_metadata", "-1",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                    final_path
                ]

            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            file_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0

            with get_db() as conn:
                conn.execute(
                    "UPDATE tasks SET status = 'READY', final_path = ?, file_size = ?, progress = 100.0 WHERE id = ?",
                    (final_path, file_size, task_id)
                )
            print(f"[FFmpeg] Hoàn tất render ID #{task_id} -> {final_path}")

        except Exception as e:
            print(f"[FFmpeg] Lỗi render ID #{task_id}: {e}")
            with get_db() as conn:
                conn.execute(
                    "UPDATE tasks SET status = 'FAILED', error_log = ? WHERE id = ?",
                    (str(e)[:200], task_id)
                )


# ==================== 6. WORKER 4: TỰ ĐỘNG ĐĂNG BÀI (PLAYWRIGHT) ====================
def human_delay(min_sec=1.5, max_sec=3.5):
    time.sleep(random.uniform(min_sec, max_sec))


def post_to_tiktok(context, video_path: str, caption: str):
    page = context.new_page()
    try:
        page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="networkidle", timeout=60000)
        human_delay(3, 5)

        page.locator('input[type="file"]').first.set_input_files(video_path)
        print("[TikTok] Đang tải video lên...")
        human_delay(8, 12)

        caption_box = page.locator('[contenteditable="true"]').first
        caption_box.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        human_delay(0.5, 1.0)
        page.keyboard.type(caption, delay=35)
        human_delay(2, 4)

        post_btn = page.locator('button:has-text("Đăng"), button:has-text("Post")').last
        post_btn.wait_for(state="visible", timeout=60000)
        post_btn.click()
        human_delay(5, 8)
        print("[TikTok] Đã đăng thành công!")
    finally:
        page.close()


def post_to_facebook_reels(context, video_path: str, caption: str):
    page = context.new_page()
    try:
        page.goto("https://www.facebook.com/reels/create", wait_until="networkidle", timeout=60000)
        human_delay(3, 5)

        page.locator('input[type="file"]').first.set_input_files(video_path)
        print("[Facebook Reels] Đang tải video lên...")
        human_delay(6, 10)

        for _ in range(2):
            next_btn = page.locator('div[role="button"]:has-text("Tiếp"), div[role="button"]:has-text("Next")').last
            if next_btn.is_visible():
                next_btn.click()
                human_delay(2, 3.5)

        desc_box = page.locator('div[role="textbox"]').first
        if desc_box.is_visible():
            desc_box.click()
            page.keyboard.type(caption, delay=35)
            human_delay(1.5, 3)

        publish_btn = page.locator('div[role="button"]:has-text("Đăng"), div[role="button"]:has-text("Publish")').last
        publish_btn.wait_for(state="visible", timeout=60000)
        publish_btn.click()
        human_delay(5, 8)
        print("[Facebook Reels] Đã đăng thành công!")
    finally:
        page.close()


def post_to_threads(context, video_path: str, caption: str):
    page = context.new_page()
    try:
        page.goto("https://www.threads.net/", wait_until="networkidle", timeout=60000)
        human_delay(3, 5)

        create_btn = page.locator('div[role="button"]:has-text("Tạo"), div[role="button"]:has-text("Create"), svg[aria-label="Tạo"], svg[aria-label="Create"]').first
        create_btn.click()
        human_delay(2, 3)

        page.locator('input[type="file"]').first.set_input_files(video_path)
        print("[Threads] Đang tải video lên...")
        human_delay(6, 10)

        text_box = page.locator('div[role="textbox"]').first
        text_box.click()
        page.keyboard.type(caption, delay=35)
        human_delay(2, 3)

        post_btn = page.locator('div[role="button"]:has-text("Đăng"), div[role="button"]:has-text("Post")').last
        post_btn.wait_for(state="visible", timeout=60000)
        post_btn.click()
        human_delay(5, 8)
        print("[Threads] Đã đăng thành công!")
    finally:
        page.close()


def upload_worker():
    while True:
        with get_db() as conn:
            task = conn.execute(
                "SELECT * FROM tasks WHERE status = 'READY' ORDER BY id ASC LIMIT 1"
            ).fetchone()

        if not task:
            time.sleep(3)
            continue

        task_id, final_path, title = task["id"], task["final_path"], task["title"]
        print(f"[Uploader] Bắt đầu phân phối ID #{task_id}: {title[:45]}")

        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=PROFILE_DIR,
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 800}
                )
                try:
                    if ENABLE_TIKTOK:
                        post_to_tiktok(context, final_path, title)
                    if ENABLE_FACEBOOK_REELS:
                        post_to_facebook_reels(context, final_path, title)
                    if ENABLE_THREADS:
                        post_to_threads(context, final_path, title)
                finally:
                    context.close()

            with get_db() as conn:
                conn.execute("UPDATE tasks SET status = 'DONE' WHERE id = ?", (task_id,))
            print(f"[Uploader] Hoàn tất ID #{task_id}. Tạm nghỉ {UPLOAD_DELAY_SECONDS}s...")
            time.sleep(UPLOAD_DELAY_SECONDS)

        except Exception as e:
            err_msg = str(e)[:200]
            print(f"[Uploader] Lỗi đăng bài ID #{task_id}: {err_msg}")
            with get_db() as conn:
                conn.execute("""
                    UPDATE tasks
                    SET retry_count = retry_count + 1,
                        error_log = ?,
                        status = CASE WHEN retry_count >= 2 THEN 'FAILED' ELSE 'READY' END
                    WHERE id = ?
                """, (err_msg, task_id))
            time.sleep(30)


# ==================== 7. TIỆN ÍCH ĐĂNG NHẬP & KIỂM TRA ====================
def run_login_session():
    print("Đang mở trình duyệt lưu phiên...")
    print("Hãy đăng nhập vào TikTok, Facebook và Threads trên 3 tab vừa mở, sau đó đóng trình duyệt.")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800}
        )
        p1 = context.pages[0] if context.pages else context.new_page()
        p1.goto("https://www.tiktok.com/login")
        p2 = context.new_page()
        p2.goto("https://www.facebook.com/")
        p3 = context.new_page()
        p3.goto("https://www.threads.net/login")

        try:
            while len(context.pages) > 0:
                time.sleep(1)
        except Exception:
            pass

        # Xuất cookies sang data/cookies.txt
        try:
            cookies = context.cookies()
            cookie_path = os.path.join(DATA_DIR, "cookies.txt")
            with open(cookie_path, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\n")
                for c in cookies:
                    domain = c.get("domain", "")
                    flag = "TRUE" if domain.startswith(".") else "FALSE"
                    path = c.get("path", "/")
                    secure = "TRUE" if c.get("secure") else "FALSE"
                    expires = int(c.get("expires", 0)) if c.get("expires") else 0
                    name = c.get("name", "")
                    val = c.get("value", "")
                    f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{val}\n")
            print(f">> Đã tự động xuất {len(cookies)} cookies vào data/cookies.txt!")
        except Exception:
            pass

    print("Đã lưu toàn bộ Cookie đăng nhập thành công!")


def show_status():
    init_db()
    with get_db() as conn:
        rows = conn.execute("SELECT id, status, retry_count, title, error_log FROM tasks ORDER BY id DESC LIMIT 20").fetchall()
    print(f"\n{'ID':<5} | {'TRẠNG THÁI':<12} | {'THỬ LẠI':<8} | {'TIÊU ĐỀ / LỖI'}")
    print("-" * 75)
    for r in rows:
        info = r["error_log"] if r["status"] == "FAILED" else (r["title"] or "Đang chờ...")
        print(f"{r['id']:<5} | {r['status']:<12} | {r['retry_count']:<8} | {info[:45]}")
    print()


# ==================== 8. ĐIỂM KHỞI CHẠY CHÍNH ====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hệ thống tự động tải, biên tập và đăng video đa kênh.")
    parser.add_argument("--login", action="store_true", help="Mở trình duyệt để đăng nhập lưu Cookie")
    parser.add_argument("--status", action="store_true", help="Xem danh sách trạng thái 20 video gần nhất")
    args = parser.parse_args()

    if args.login:
        run_login_session()
        sys.exit(0)

    if args.status:
        show_status()
        sys.exit(0)

    init_db()

    # Bật các công nhân chạy đa luồng song song
    threading.Thread(target=clipboard_watcher, daemon=True).start()
    for i in range(3):
        threading.Thread(target=download_worker, args=(i + 1,), daemon=True).start()
    threading.Thread(target=process_worker, daemon=True).start()
    threading.Thread(target=upload_worker, daemon=True).start()

    print("==========================================================")
    print("HỆ THỐNG ĐANG CHẠY NGẦM! Chỉ cần copy link video để nạp.")
    print("Gõ 'python auto_reup_pro.py --status' ở cửa sổ khác để xem tiến độ.")
    print("==========================================================")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nĐã dừng hệ thống an toàn.")
