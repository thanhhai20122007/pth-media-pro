import os
import re
import sys
import time
import subprocess
import threading
from typing import Optional
from core.config import BIN_DIR

_TUNNEL_PROC: Optional[subprocess.Popen] = None
_PUBLIC_URL: Optional[str] = None
_REMOTE_TUNNEL_URL: Optional[str] = None
_REMOTE_TUNNEL_TIME: float = 0.0


def get_public_tunnel_url() -> Optional[str]:
    global _PUBLIC_URL
    return _PUBLIC_URL


def set_remote_tunnel_url(url: str):
    """Lưu trữ link Tunnel của Node máy tính được đăng ký lên Cloud Render"""
    global _REMOTE_TUNNEL_URL, _REMOTE_TUNNEL_TIME
    _REMOTE_TUNNEL_URL = (url or "").strip().rstrip("/")
    _REMOTE_TUNNEL_TIME = time.time()


def get_remote_tunnel_url() -> Optional[str]:
    """Lấy link Node máy tính nếu còn hoạt động trong vòng 3 phút"""
    global _REMOTE_TUNNEL_URL, _REMOTE_TUNNEL_TIME
    if _REMOTE_TUNNEL_URL and (time.time() - _REMOTE_TUNNEL_TIME < 180):
        return _REMOTE_TUNNEL_URL
    return None


def start_tunnel(port: int = 5000) -> Optional[str]:
    """
    Khởi động Cloudflare Quick Tunnel hoàn toàn miễn phí, không cần tài khoản,
    cấp phát đường dẫn HTTPS toàn cầu để điện thoại 4G/5G vào được từ bất kỳ đâu.
    """
    global _TUNNEL_PROC, _PUBLIC_URL
    cloudflared_exe = os.path.join(BIN_DIR, "cloudflared.exe")
    if not os.path.exists(cloudflared_exe):
        return None

    cmd = [cloudflared_exe, "tunnel", "--url", f"http://127.0.0.1:{port}"]

    try:
        _TUNNEL_PROC = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
    except Exception as e:
        print(f"[CloudflareTunnel] Không thể khởi chạy: {e}")
        return None

    # Đọc log để trích xuất link https://*.trycloudflare.com
    t0 = time.time()
    while time.time() - t0 < 15:
        line = _TUNNEL_PROC.stdout.readline()
        if not line:
            time.sleep(0.2)
            continue
        m = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
        if m:
            _PUBLIC_URL = m.group(0)
            print(f"[CloudflareTunnel] 🌐 Link Public Toàn Cầu: {_PUBLIC_URL}")

            # Lưu link ra file để tiện tra cứu hoặc hiển thị
            try:
                os.makedirs(os.path.join(os.path.dirname(BIN_DIR), "data"), exist_ok=True)
                with open(os.path.join(os.path.dirname(BIN_DIR), "data", "public_tunnel.txt"), "w", encoding="utf-8") as f:
                    f.write(_PUBLIC_URL)
            except Exception:
                pass

            # Khởi động luồng đọc nền để tránh đầy buffer
            def drain_pipe(proc):
                while proc.poll() is None:
                    proc.stdout.readline()
            threading.Thread(target=drain_pipe, args=(_TUNNEL_PROC,), daemon=True).start()

            # Luồng đồng bộ Heartbeat lên Cloud Render để điện thoại mở pth-media-pro.onrender.com tự nhận diện máy tính
            def sync_to_cloud(tunnel_url: str):
                import requests
                while True:
                    try:
                        requests.post(
                            "https://pth-media-pro.onrender.com/api/tunnel/register",
                            json={"tunnel_url": tunnel_url},
                            timeout=10
                        )
                    except Exception:
                        pass
                    time.sleep(45)  # Cứ 45 giây gửi heartbeat 1 lần để Cloud luôn nhận diện Node

            threading.Thread(target=sync_to_cloud, args=(_PUBLIC_URL,), daemon=True).start()

            return _PUBLIC_URL

    return _PUBLIC_URL


def stop_tunnel():
    global _TUNNEL_PROC
    if _TUNNEL_PROC:
        try:
            _TUNNEL_PROC.terminate()
        except Exception:
            pass
        _TUNNEL_PROC = None
