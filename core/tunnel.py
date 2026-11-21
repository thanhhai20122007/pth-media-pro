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


def get_public_tunnel_url() -> Optional[str]:
    global _PUBLIC_URL
    return _PUBLIC_URL


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
            # Khởi động luồng đọc nền để tránh đầy buffer
            def drain_pipe(proc):
                while proc.poll() is None:
                    proc.stdout.readline()
            threading.Thread(target=drain_pipe, args=(_TUNNEL_PROC,), daemon=True).start()
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
