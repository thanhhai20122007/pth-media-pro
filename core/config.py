import os
import sys

# Thư mục gốc dự án
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cấu hình đường dẫn FFmpeg & Tools (Tự động thích ứng cả Windows và Linux Docker Cloud)
BIN_DIR = os.path.join(BASE_DIR, "bin")
if sys.platform == "win32":
    FFMPEG_EXE = os.path.join(BIN_DIR, "ffmpeg.exe") if os.path.exists(os.path.join(BIN_DIR, "ffmpeg.exe")) else "ffmpeg"
    FFPROBE_EXE = os.path.join(BIN_DIR, "ffprobe.exe") if os.path.exists(os.path.join(BIN_DIR, "ffprobe.exe")) else "ffprobe"
else:
    FFMPEG_EXE = "ffmpeg"
    FFPROBE_EXE = "ffprobe"

# Thêm BIN_DIR vào PATH nếu chưa có
if os.path.exists(BIN_DIR) and BIN_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")

# Các thư mục lưu trữ
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
VIDEOS_DIR = os.path.join(DOWNLOADS_DIR, "videos")
AUDIOS_DIR = os.path.join(DOWNLOADS_DIR, "audios")
PROCESSED_DIR = os.path.join(DOWNLOADS_DIR, "processed")
WATERMARKED_DIR = os.path.join(DOWNLOADS_DIR, "watermarked")

DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
DB_PATH = os.path.join(DATA_DIR, "tasks.db")
COOKIE_FILE = os.path.join(DATA_DIR, "cookies.txt")

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

PROFILES_DIR = os.path.join(BASE_DIR, "profiles")
BROWSER_DATA_DIR = os.path.join(PROFILES_DIR, "browser_data")

# Tạo toàn bộ thư mục nếu chưa tồn tại
for folder in (
    BIN_DIR,
    DOWNLOADS_DIR,
    VIDEOS_DIR,
    AUDIOS_DIR,
    PROCESSED_DIR,
    WATERMARKED_DIR,
    DATA_DIR,
    RAW_DIR,
    ASSETS_DIR,
    PROFILES_DIR,
    BROWSER_DATA_DIR,
):
    os.makedirs(folder, exist_ok=True)

# Danh sách tên miền hỗ trợ
SUPPORTED_DOMAINS = (
    "tiktok.com",
    "douyin.com",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "fb.watch",
    "fb.com",
    "instagram.com",
    "threads.net",
    "twitter.com",
    "x.com",
    "kuaishou.com",
    "kwai.com",
    "pinterest.com",
    "pin.it",
    "xiaohongshu.com",
    "xhslink.com",
    "bilibili.com",
    "capcut.com",
)

# Cấu hình mặc định
DEFAULT_SETTINGS = {
    "auto_clipboard": True,
    "anti_duplicate": False,
    "download_mode": "video",  # video | audio | processed
    "target_resolution": "1080x1920",  # 1080x1920 (9:16) | original
    "speed_factor": 1.02,
    "zoom_factor": 1.02,
    "blur_background": True,  # Tạo nền mờ hai bên cho video 9:16
    "strip_metadata": True,
    "watermark_enabled": False,
    "watermark_position": "top_right",  # top_right | top_left | bottom_right | bottom_left
    "watermark_opacity": 0.85,
    "custom_hashtags": "#xuhuong #viral #reels #shorts",
    "max_concurrent_downloads": 4,  # Số tác vụ tải song song cùng lúc (1-10)
    "web_port": 5000,
}


def open_folder_in_explorer(path: str):
    """Mở thư mục hoặc chọn file trong Windows Explorer"""
    try:
        norm_path = os.path.normpath(path)
        if os.path.isfile(norm_path):
            os.system(f'explorer.exe /select,"{norm_path}"')
        elif os.path.isdir(norm_path):
            os.system(f'explorer.exe "{norm_path}"')
        else:
            os.system(f'explorer.exe "{DOWNLOADS_DIR}"')
        return True
    except Exception as e:
        print(f"Lỗi mở Explorer: {e}")
        return False
