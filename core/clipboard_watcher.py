import time
import threading
import pyperclip
from typing import Optional, Callable
from core.config import SUPPORTED_DOMAINS
from core.database import add_task, get_setting


class ClipboardWatcher:
    def __init__(self, on_new_link: Optional[Callable[[str, int], None]] = None):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_text = ""
        self.on_new_link = on_new_link

    def is_running(self) -> bool:
        return self._running

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[ClipboardWatcher] Đã kích hoạt giám sát Clipboard ngầm...")

    def stop(self):
        self._running = False
        print("[ClipboardWatcher] Đã tạm dừng giám sát Clipboard.")

    def _loop(self):
        while self._running:
            try:
                # Kiểm tra cài đặt bật/tắt từ database
                is_enabled = get_setting("auto_clipboard", True)
                if not is_enabled:
                    time.sleep(1.5)
                    continue

                text = pyperclip.paste().strip()
                if text and text != self._last_text and text.startswith("http"):
                    self._last_text = text
                    # Kiểm tra xem có chứa tên miền hỗ trợ không
                    text_lower = text.lower()
                    if any(domain in text_lower for domain in SUPPORTED_DOMAINS):
                        # Lấy chế độ tải mặc định từ cài đặt
                        mode = get_setting("download_mode", "video")
                        task_id = add_task(text, format_type=mode)
                        if task_id:
                            print(f"\n[ClipboardWatcher] 🔥 Bắt được link mới: {text} (Task #{task_id})")
                            if self.on_new_link:
                                try:
                                    self.on_new_link(text, task_id)
                                except Exception as cb_err:
                                    print(f"Lỗi callback clipboard: {cb_err}")

            except Exception:
                pass
            time.sleep(0.8)


# Singleton instance
clipboard_watcher = ClipboardWatcher()
