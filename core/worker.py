import os
import time
import threading
from typing import Optional, Callable, List
from core.database import (
    claim_next_pending_task,
    update_task,
    update_task_progress,
    get_setting,
)
from core.downloader import download_video_smart
from core.processor import apply_anti_duplicate_filter, apply_custom_watermark
from core.config import PROCESSED_DIR, WATERMARKED_DIR


class TaskWorker:
    """
    HỆ THỐNG CÔNG NHÂN XỬ LÝ HÀNG ĐỢI ĐA LUỒNG SONG SONG (MULTITHREADING POOL):
    Cho phép tải đồng thời 3 - 8 video cùng một lúc, tăng tốc độ xử lý hàng loạt lên gấp nhiều lần.
    """
    def __init__(self, broadcast_callback: Optional[Callable[[dict], None]] = None):
        self._running = False
        self._threads: List[threading.Thread] = []
        self.broadcast_callback = broadcast_callback
        self.num_workers = 4

    def is_running(self) -> bool:
        return self._running

    def start(self, num_workers: Optional[int] = None):
        if self._running:
            return
        self._running = True

        # Đọc cấu hình số luồng tải song song từ Database
        if num_workers is not None:
            self.num_workers = num_workers
        else:
            try:
                self.num_workers = int(get_setting("max_concurrent_downloads", 4))
            except Exception:
                self.num_workers = 4

        self.num_workers = max(1, min(self.num_workers, 10))
        self._threads = []

        for i in range(self.num_workers):
            t = threading.Thread(target=self._worker_loop, args=(i + 1,), daemon=True)
            t.start()
            self._threads.append(t)

        print(f"[TaskWorkerPool] Đã kích hoạt {self.num_workers} công nhân tải song song!")

    def stop(self):
        self._running = False

    def notify_ui(self, event_type: str, data: dict):
        if self.broadcast_callback:
            try:
                self.broadcast_callback({"event": event_type, "data": data})
            except Exception:
                pass

    def _worker_loop(self, worker_id: int):
        while self._running:
            # Lấy và khóa nguyên tử 1 task PENDING tiếp theo (không bao giờ bị trùng giữa các worker)
            task = claim_next_pending_task()
            if not task:
                time.sleep(0.6)
                continue

            task_id = task["id"]
            url = task["url"]
            format_type = task.get("format_type", "video")
            quality = task.get("quality", "1080p")
            session_id = task.get("session_id", "default")

            print(f"[Worker #{worker_id}] Bắt đầu tải Task #{task_id}: {url[:60]}")
            self.notify_ui("task_start", {"id": task_id, "session_id": session_id, "status": "DOWNLOADING", "worker_id": worker_id})

            try:
                # 1. TẢI VIDEO SẠCH / KHÔNG LOGO
                def prog_cb(pct: float, speed: str):
                    update_task_progress(task_id, round(pct, 1), speed=speed)
                    self.notify_ui("task_progress", {
                        "id": task_id,
                        "session_id": session_id,
                        "progress": round(pct, 1),
                        "speed": speed,
                        "status": "DOWNLOADING"
                    })

                dl_info = download_video_smart(url, task_id, format_type, quality=quality, progress_callback=prog_cb)
                if not dl_info or not isinstance(dl_info, dict):
                    raise Exception("Không thể lấy thông tin tệp tải về từ máy chủ")

                raw_path = dl_info.get("file_path")
                if not raw_path or not os.path.exists(raw_path):
                    raise Exception("Tệp video sau khi tải không tồn tại")
                title = dl_info.get("title", "Video")
                author = dl_info.get("author", "")
                thumbnail = dl_info.get("thumbnail", "")
                duration = dl_info.get("duration", 0)
                file_size = dl_info.get("file_size", 0)
                platform = dl_info.get("platform", "general")

                update_task(
                    task_id,
                    title=title,
                    author=author,
                    thumbnail=thumbnail,
                    duration=duration,
                    file_size=file_size,
                    platform=platform,
                    raw_path=raw_path
                )

                current_path = raw_path

                # 2. XỬ LÝ HẬU KỲ CHỐNG TRÙNG LẶP (NẾU ĐƯỢC BẬT HOẶC YÊU CẦU)
                is_anti_dup = get_setting("anti_duplicate", False) or (format_type == "processed")
                if is_anti_dup and format_type != "audio" and current_path and os.path.exists(current_path):
                    update_task_progress(task_id, 50.0, speed="FFmpeg", status="PROCESSING")
                    self.notify_ui("task_progress", {
                        "id": task_id,
                        "session_id": session_id,
                        "progress": 50.0,
                        "speed": "Đang lách 9:16",
                        "status": "PROCESSING"
                    })

                    res_setting = get_setting("target_resolution", "1080x1920")
                    speed_setting = float(get_setting("speed_factor", 1.02))
                    zoom_setting = float(get_setting("zoom_factor", 1.02))
                    blur_bg = bool(get_setting("blur_background", True))

                    out_processed = os.path.join(PROCESSED_DIR, f"clean_{task_id}.mp4")
                    apply_anti_duplicate_filter(
                        input_path=current_path,
                        output_path=out_processed,
                        target_resolution=res_setting,
                        speed_factor=speed_setting,
                        zoom_factor=zoom_setting,
                        blur_background=blur_bg
                    )
                    current_path = out_processed

                # 3. XỬ LÝ ĐÓNG DẤU BẢN QUYỀN (NẾU CHỌN CHẾ ĐỘ HOẶC BẬT TỰ ĐỘNG)
                is_watermark = (format_type == "watermarked") or bool(get_setting("auto_watermark", False))
                if is_watermark and format_type != "audio" and current_path and os.path.exists(current_path):
                    update_task_progress(task_id, 75.0, speed="Đóng dấu", status="PROCESSING")
                    self.notify_ui("task_progress", {
                        "id": task_id,
                        "session_id": session_id,
                        "progress": 75.0,
                        "speed": "Đang đóng dấu",
                        "status": "PROCESSING"
                    })

                    wm_type = get_setting("watermark_type", "text")
                    wm_text = get_setting("watermark_text", "@PTH_Media")
                    wm_pos = get_setting("watermark_position", "bottom_right")
                    wm_opacity = float(get_setting("watermark_opacity", 0.85))
                    wm_font_size = int(get_setting("watermark_font_size", 36))
                    wm_font_color = get_setting("watermark_font_color", "white")
                    wm_scale = float(get_setting("watermark_scale", 0.20))
                    wm_img = get_setting("watermark_image_path", None)

                    out_watermarked = os.path.join(WATERMARKED_DIR, f"wm_{task_id}.mp4")
                    apply_custom_watermark(
                        input_path=current_path,
                        output_path=out_watermarked,
                        watermark_type=wm_type,
                        watermark_text=wm_text,
                        watermark_image_path=wm_img,
                        position=wm_pos,
                        opacity=wm_opacity,
                        font_size=wm_font_size,
                        font_color=wm_font_color,
                        scale_factor=wm_scale
                    )
                    current_path = out_watermarked

                # 4. HOÀN TẤT TÁC VỤ
                final_size = os.path.getsize(current_path) if os.path.exists(current_path) else file_size
                final_status = "READY" if (is_anti_dup or is_watermark) else "DONE"
                update_task(
                    task_id,
                    final_path=current_path,
                    file_size=final_size,
                    status=final_status,
                    progress=100.0,
                    speed="Hoàn tất",
                    error_log=None
                )
                print(f"[Worker #{worker_id}] Đã hoàn tất Task #{task_id}: {title[:40]}")
                self.notify_ui("task_done", {"id": task_id, "session_id": session_id, "status": final_status, "final_path": current_path})

            except Exception as e:
                err_msg = str(e)[:300]
                print(f"[Worker #{worker_id}] Lỗi xử lý Task #{task_id}: {err_msg}")
                retry = task.get("retry_count", 0) + 1
                new_status = "FAILED" if retry >= 3 else "PENDING"
                update_task(
                    task_id,
                    retry_count=retry,
                    error_log=err_msg,
                    status=new_status,
                    speed="Lỗi"
                )
                self.notify_ui("task_error", {"id": task_id, "session_id": session_id, "error": err_msg, "status": new_status})
                time.sleep(1.0)


# Singleton instance
task_worker = TaskWorker()
