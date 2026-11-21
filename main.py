import os
import sys
import time
import socket
import argparse
import threading
import webbrowser
import uvicorn

from core.config import BASE_DIR, FFMPEG_EXE, BIN_DIR, open_folder_in_explorer
from core.database import init_db, get_tasks, get_stats
from core.worker import task_worker
from core.clipboard_watcher import clipboard_watcher
from core.reup_engine import run_login_session
from web.app import app


def get_local_ip() -> str:
    """Lấy địa chỉ IP mạng nội bộ (Wi-Fi/LAN) của máy tính để điện thoại truy cập"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def show_terminal_status():
    """Hiển thị bảng trạng thái nhanh trong Terminal"""
    init_db()
    tasks = get_tasks(limit=25)
    stats = get_stats()

    print("\n" + "=" * 80)
    print("               PTH MEDIA PRO - BẢNG THEO DÕI TIẾN ĐỘ")
    print("=" * 80)
    print(f"Tổng: {stats['total']} | Hoàn tất: {stats['completed']} | Đang tải: {stats['pending']} | Lỗi: {stats['failed']}")
    print("-" * 80)
    print(f"{'ID':<5} | {'NỀN TẢNG':<10} | {'TRẠNG THÁI':<14} | {'TIẾN TRÌNH':<10} | {'TIÊU ĐỀ / LỖI'}")
    print("-" * 80)

    for t in tasks:
        title = t.get("error_log") if t["status"] == "FAILED" else (t.get("title") or t.get("url") or "Đang chờ...")
        pct_str = f"{t.get('progress', 0.0)}%"
        print(f"{t['id']:<5} | {t.get('platform', 'other'):<10} | {t['status']:<14} | {pct_str:<10} | {title[:35]}")
    print("=" * 80 + "\n")


def run_web_server(port: int = 5000):
    """Chạy FastAPI backend bằng Uvicorn trên 0.0.0.0 để cả máy tính và điện thoại cùng mạng Wi-Fi đều mở được"""
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def main():
    parser = argparse.ArgumentParser(description="PTH Media Pro - Hệ thống tải video đa năng thông minh không logo & lách bản quyền")
    parser.add_argument("--mode", choices=["web", "gui", "headless", "cli"], default="web", help="Chế độ chạy: web, gui, headless, cli")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)), help="Cổng chạy Web server (mặc định 5000 hoặc đọc từ PORT)")
    parser.add_argument("--status", action="store_true", help="Xem bảng trạng thái 25 video gần nhất")
    parser.add_argument("--login", action="store_true", help="Mở trình duyệt đăng nhập lưu tài khoản")
    parser.add_argument("--open-dir", action="store_true", help="Mở thư mục chứa video đã tải về")
    args = parser.parse_args()

    # 1. Mở thư mục
    if args.open_dir:
        from core.config import DOWNLOADS_DIR
        open_folder_in_explorer(DOWNLOADS_DIR)
        sys.exit(0)

    # 2. Xem trạng thái
    if args.status:
        show_terminal_status()
        sys.exit(0)

    # 3. Đăng nhập
    if args.login:
        run_login_session()
        sys.exit(0)

    local_ip = get_local_ip()

    print("=" * 70)
    print("     🚀 PTH MEDIA PRO - HỆ THỐNG TẢI & XỬ LÝ VIDEO ĐA NỀN TẢNG")
    print("=" * 70)
    print(f"[*] Thư mục hoạt động: {BASE_DIR}")
    print(f"[*] FFmpeg Path: {FFMPEG_EXE}")

    # Khởi tạo cơ sở dữ liệu SQLite
    init_db()

    # Khởi động các worker ngầm đa luồng song song
    task_worker.start()
    clipboard_watcher.start()

    # Khởi động Cloudflare Tunnel toàn cầu (bật link HTTPS miễn phí cho điện thoại 4G/5G ở bất kỳ đâu)
    from core.tunnel import start_tunnel
    threading.Thread(target=start_tunnel, args=(args.port,), daemon=True).start()

    pc_url = f"http://127.0.0.1:{args.port}"
    mobile_url = f"http://{local_ip}:{args.port}"

    print(f"[*] 💻 Link mở trên Máy tính:        {pc_url}")
    print(f"[*] 📱 Link nội bộ (cùng Wi-Fi):      {mobile_url}")
    print(f"[*] 🌐 Đang tạo Link Toàn Cầu (4G/5G): Tự động cấp qua Cloudflare...")
    print("[*] 📋 Đang giám sát Clipboard:       Tự động bắt link khi copy!")
    print("=" * 70)

    if args.mode == "gui":
        try:
            import webview
            t = threading.Thread(target=run_web_server, args=(args.port,), daemon=True)
            t.start()
            time.sleep(1.2)
            webview.create_window(
                "PTH Media Pro",
                pc_url,
                width=1280,
                height=850,
                resizable=True,
                background_color="#0f172a"
            )
            webview.start()
            sys.exit(0)
        except Exception as e:
            print(f"Không thể khởi động Webview GUI ({e}), chuyển sang chế độ Web...")

    if args.mode == "web":
        def open_browser():
            time.sleep(1.2)
            webbrowser.open(pc_url)

        threading.Thread(target=open_browser, daemon=True).start()
        run_web_server(args.port)

    elif args.mode in ("headless", "cli"):
        run_web_server(args.port)


if __name__ == "__main__":
    main()
