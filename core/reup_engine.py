import os
import re
import time
import random
from typing import Optional
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
from core.config import BROWSER_DATA_DIR, DEFAULT_SETTINGS
from core.database import get_setting, update_task, get_tasks


def human_delay(min_sec: float = 1.5, max_sec: float = 3.5):
    time.sleep(random.uniform(min_sec, max_sec))


def clean_caption(raw_title: str) -> str:
    """Loại bỏ hashtag cũ, cắt gọn và gắn hashtag cấu hình riêng."""
    custom_hashtags = get_setting("custom_hashtags", "#xuhuong #viral #reels #shorts")
    cleaned = re.sub(r"#\S+", "", raw_title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "Khoảnh khắc tuyệt vời mỗi ngày"
    return f"{cleaned[:120]} {custom_hashtags}".strip()


def run_login_session():
    """Mở trình duyệt Playwright để người dùng đăng nhập tài khoản một lần và lưu Cookie."""
    if sync_playwright is None:
        print("[ReupEngine] Playwright chưa được cài đặt.")
        return

    print("=" * 60)
    print("Đang mở trình duyệt để lưu phiên đăng nhập...")
    print("Hãy đăng nhập TikTok, Facebook, Threads trên các tab, sau đó chỉ cần tắt trình duyệt.")
    if sync_playwright is None:
        print("[ReupEngine] Playwright chưa được cài đặt.")
        return

    print("=" * 60)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA_DIR,
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

        # Xuất toàn bộ cookies sang định dạng Netscape cookies.txt cho yt-dlp dùng chung
        try:
            cookies = context.cookies()
            cookie_path = os.path.join(os.path.dirname(BROWSER_DATA_DIR), "..", "data", "cookies.txt")
            os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
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
        except Exception as ce:
            print(f"Lưu cookies.txt lỗi nhẹ: {ce}")

    print(">> Đã lưu toàn bộ thông tin đăng nhập thành công vào thư mục profiles/browser_data!")


def post_to_tiktok(context, video_path: str, caption: str):
    page = context.new_page()
    try:
        page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="networkidle", timeout=60000)
        human_delay(3, 5)

        page.locator('input[type="file"]').first.set_input_files(video_path)
        print("[TikTok] Đang tải tệp video lên...")
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
        print("[TikTok] Đã đăng bài thành công!")
    finally:
        page.close()


def post_to_facebook_reels(context, video_path: str, caption: str):
    page = context.new_page()
    try:
        page.goto("https://www.facebook.com/reels/create", wait_until="networkidle", timeout=60000)
        human_delay(3, 5)

        page.locator('input[type="file"]').first.set_input_files(video_path)
        print("[Facebook Reels] Đang tải tệp video lên...")
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

        create_btn = page.locator(
            'div[role="button"]:has-text("Tạo"), div[role="button"]:has-text("Create"), svg[aria-label="Tạo"], svg[aria-label="Create"]'
        ).first
        create_btn.click()
        human_delay(2, 3)

        page.locator('input[type="file"]').first.set_input_files(video_path)
        print("[Threads] Đang tải tệp video lên...")
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
