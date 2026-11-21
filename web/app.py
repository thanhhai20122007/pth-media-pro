import os
import re
import time
import json
import asyncio
import mimetypes
from typing import List, Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Header
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.config import (
    BASE_DIR,
    DOWNLOADS_DIR,
    VIDEOS_DIR,
    AUDIOS_DIR,
    PROCESSED_DIR,
    open_folder_in_explorer,
)
from core.database import (
    get_tasks,
    get_task,
    add_task,
    delete_task,
    update_task,
    get_stats,
    get_all_settings,
    set_setting,
    get_setting,
)
from core.processor import apply_anti_duplicate_filter, extract_audio_mp3, compress_video
from core.downloader import sanitize_filename, extract_playlist_or_channel
from core.ai_engine import (
    apply_ai_autocaptions,
    apply_ai_voiceover_dubbing,
    extract_smart_viral_clips,
    detect_existing_subtitles,
)
from core.worker import task_worker
from core.clipboard_watcher import clipboard_watcher

app = FastAPI(title="PTH Media Pro", description="Hệ thống tải video đa năng không logo & lách bản quyền thông minh")

# Thư mục web
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(WEB_DIR, "static")
TEMPLATES_DIR = os.path.join(WEB_DIR, "templates")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Quản lý WebSocket kết nối từ UI hỗ trợ phân tách phiên người dùng độc lập
class ConnectionManager:
    def __init__(self):
        # session_id -> list of active WebSockets
        self.sessions: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str = "default"):
        await websocket.accept()
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        self.sessions[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str = "default"):
        if session_id in self.sessions and websocket in self.sessions[session_id]:
            self.sessions[session_id].remove(websocket)
            if not self.sessions[session_id]:
                del self.sessions[session_id]

    async def broadcast(self, message: dict):
        target_session = message.get("session_id") or (
            message.get("data") and message["data"].get("session_id")
        )
        
        # Nếu có session_id cụ thể, chỉ gửi cho các máy/thiết bị thuộc phiên đó
        if target_session and target_session in self.sessions:
            targets = [(ws, target_session) for ws in list(self.sessions[target_session])]
        elif not target_session:
            # Thông báo toàn cục (cài đặt hệ thống, trạng thái chung)
            targets = [(ws, sid) for sid, conns in self.sessions.items() for ws in list(conns)]
        else:
            targets = []

        for ws, sid in targets:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws, sid)


ws_manager = ConnectionManager()
loop_ref = None


def broadcast_sync(msg: dict):
    """Gửi thông điệp từ luồng nền (thread) sang WebSocket async"""
    global loop_ref
    if loop_ref and loop_ref.is_running():
        asyncio.run_coroutine_threadsafe(ws_manager.broadcast(msg), loop_ref)


# Đăng ký callback cho worker và clipboard watcher
task_worker.broadcast_callback = broadcast_sync


def on_clipboard_link(url: str, task_id: int):
    broadcast_sync({
        "event": "clipboard_detected",
        "data": {"url": url, "id": task_id, "message": f"Đã bắt link từ Clipboard: {url[:50]}..."}
    })


clipboard_watcher.on_new_link = on_clipboard_link


# ==================== CÁC SCHEMA REQUEST ====================
class SingleTaskRequest(BaseModel):
    url: str
    format_type: Optional[str] = "video"  # video | audio | processed
    quality: Optional[str] = "1080p"      # 720p | 1080p | 4k | audio
    session_id: Optional[str] = "default"


class BatchTaskRequest(BaseModel):
    urls: List[str]
    format_type: Optional[str] = "video"
    quality: Optional[str] = "1080p"
    session_id: Optional[str] = "default"


class PlaylistExtractRequest(BaseModel):
    url: str
    max_items: Optional[int] = 30
    format_type: Optional[str] = "video"
    quality: Optional[str] = "1080p"
    session_id: Optional[str] = "default"


class AutoCaptionRequest(BaseModel):
    task_id: int
    style_preset: Optional[str] = "capcut_yellow"
    position: Optional[str] = "bottom"
    skip_if_exists: Optional[bool] = True


class VoiceoverDubbingRequest(BaseModel):
    task_id: int
    voice_type: Optional[str] = "male_north"


class HighlightsRequest(BaseModel):
    task_id: int
    num_clips: Optional[int] = 3
    clip_duration: Optional[int] = 45
    crop_mode: Optional[str] = "blur"


class SettingsRequest(BaseModel):
    auto_clipboard: Optional[bool] = None
    anti_duplicate: Optional[bool] = None
    download_mode: Optional[str] = None
    target_resolution: Optional[str] = None
    speed_factor: Optional[float] = None
    zoom_factor: Optional[float] = None
    blur_background: Optional[bool] = None
    watermark_enabled: Optional[bool] = None
    watermark_position: Optional[str] = None
    custom_hashtags: Optional[str] = None
    max_concurrent_downloads: Optional[int] = None


class OpenFolderRequest(BaseModel):
    path: Optional[str] = None
    type: Optional[str] = "all"  # all | videos | audios | processed


# ==================== WEBSOCKET ====================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: Optional[str] = "default"):
    global loop_ref
    loop_ref = asyncio.get_running_loop()
    sid = session_id or "default"
    await ws_manager.connect(websocket, sid)
    try:
        while True:
            # Nhận ping từ client để giữ kết nối
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, sid)
    except Exception:
        ws_manager.disconnect(websocket, sid)


# ==================== API ENDPOINTS ====================
@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>PTH Media Pro - Đang tải giao diện...</h1>")


@app.get("/api/tasks")
async def api_get_tasks(limit: int = 50, status: Optional[str] = None, session_id: Optional[str] = None):
    return {"tasks": get_tasks(limit=limit, status=status, session_id=session_id)}


@app.post("/api/tasks")
async def api_add_task(req: SingleTaskRequest):
    text = req.url.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Vui lòng nhập đường dẫn URL")

    sid = req.session_id or "default"
    quality = req.quality or "1080p"

    # Nhận diện thông minh: Cho phép dán đồng thời nhiều link cách nhau bởi khoảng trắng hoặc xuống dòng
    urls = re.findall(r'https?://[^\s,;"\'<>]+', text)
    if len(urls) > 1:
        added_ids = []
        for u in urls:
            t_id = add_task(u, format_type=req.format_type, session_id=sid, quality=quality)
            if t_id:
                added_ids.append(t_id)
        broadcast_sync({"event": "batch_added", "session_id": sid, "data": {"count": len(added_ids), "session_id": sid}})
        return {"status": "success", "count": len(added_ids), "ids": added_ids}

    # Nếu chỉ có 1 link
    target_url = urls[0] if urls else text
    task_id = add_task(target_url, format_type=req.format_type, session_id=sid, quality=quality)
    if not task_id:
        raise HTTPException(status_code=500, detail="Không thể tạo tác vụ tải")
    broadcast_sync({"event": "task_added", "session_id": sid, "data": {"id": task_id, "url": target_url, "session_id": sid}})
    return {"status": "success", "id": task_id}


@app.post("/api/tasks/batch")
async def api_add_batch(req: BatchTaskRequest):
    sid = req.session_id or "default"
    quality = req.quality or "1080p"
    added_ids = []
    for u in req.urls:
        clean_u = u.strip()
        if clean_u.startswith("http"):
            t_id = add_task(clean_u, format_type=req.format_type, session_id=sid, quality=quality)
            if t_id:
                added_ids.append(t_id)
    broadcast_sync({"event": "batch_added", "session_id": sid, "data": {"count": len(added_ids), "session_id": sid}})
    return {"status": "success", "count": len(added_ids), "ids": added_ids}


@app.post("/api/playlist/extract")
async def api_extract_playlist(req: PlaylistExtractRequest):
    """
    Bóc tách và tải hàng loạt video từ kênh hoặc playlist
    """
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp URL kênh hoặc playlist")
    sid = req.session_id or "default"
    quality = req.quality or "1080p"

    try:
        data = extract_playlist_or_channel(url, max_items=req.max_items or 30)
        videos = data.get("videos", [])
        added_ids = []
        for v in videos:
            t_id = add_task(
                url=v["url"],
                format_type=req.format_type or "video",
                title=v.get("title"),
                session_id=sid,
                quality=quality
            )
            if t_id:
                added_ids.append(t_id)

        broadcast_sync({"event": "batch_added", "session_id": sid, "data": {"count": len(added_ids), "session_id": sid}})
        return {
            "status": "success",
            "title": data.get("title"),
            "uploader": data.get("uploader"),
            "total_found": data.get("count"),
            "added_count": len(added_ids),
            "ids": added_ids
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi bóc tách kênh/playlist: {str(e)[:200]}")


@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: int, delete_file: bool = False):
    task = get_task(task_id)
    sid = task.get("session_id", "default") if task else "default"
    success = delete_task(task_id, delete_file=delete_file)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    broadcast_sync({"event": "task_deleted", "session_id": sid, "data": {"id": task_id, "session_id": sid}})
    return {"status": "success"}


@app.post("/api/tasks/{task_id}/retry")
async def api_retry_task(task_id: int):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    sid = task.get("session_id", "default")
    update_task(task_id, status="PENDING", retry_count=0, progress=0.0, speed="", error_log="")
    broadcast_sync({"event": "task_retry", "session_id": sid, "data": {"id": task_id, "session_id": sid}})
    return {"status": "success"}


@app.post("/api/tasks/{task_id}/process")
async def api_process_task(task_id: int, bg_tasks: BackgroundTasks):
    task = get_task(task_id)
    if not task or not task.get("raw_path") or not os.path.exists(task["raw_path"]):
        raise HTTPException(status_code=400, detail="Tệp gốc không tồn tại để xử lý")
    sid = task.get("session_id", "default")

    def run_proc():
        try:
            update_task(task_id, status="PROCESSING", progress=30.0, speed="FFmpeg")
            broadcast_sync({"event": "task_progress", "session_id": sid, "data": {"id": task_id, "session_id": sid, "status": "PROCESSING", "progress": 30.0}})
            out_processed = os.path.join(PROCESSED_DIR, f"clean_{task_id}.mp4")
            apply_anti_duplicate_filter(
                input_path=task["raw_path"],
                output_path=out_processed,
                target_resolution=get_setting("target_resolution", "1080x1920"),
                speed_factor=float(get_setting("speed_factor", 1.02)),
                zoom_factor=float(get_setting("zoom_factor", 1.02)),
                blur_background=bool(get_setting("blur_background", True))
            )
            update_task(task_id, final_path=out_processed, status="READY", progress=100.0, speed="Hoàn tất")
            broadcast_sync({"event": "task_done", "session_id": sid, "data": {"id": task_id, "session_id": sid, "status": "READY", "final_path": out_processed}})
        except Exception as e:
            update_task(task_id, status="FAILED", error_log=str(e)[:200])
            broadcast_sync({"event": "task_error", "session_id": sid, "data": {"id": task_id, "session_id": sid, "error": str(e)[:200]}})

    bg_tasks.add_task(run_proc)
    return {"status": "processing_started"}


@app.post("/api/tasks/{task_id}/extract-audio")
async def api_extract_audio(task_id: int, bg_tasks: BackgroundTasks):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    src_path = task.get("final_path") or task.get("raw_path")
    if not src_path or not os.path.exists(src_path):
        raise HTTPException(status_code=400, detail="Không tìm thấy tệp video để tách nhạc")
    sid = task.get("session_id", "default")

    def run_audio():
        try:
            update_task(task_id, speed="Tách MP3", progress=50.0)
            out_mp3 = extract_audio_mp3(src_path)
            update_task(task_id, final_path=out_mp3, format_type="audio", speed="Đã tách MP3", progress=100.0, status="DONE")
            broadcast_sync({"event": "task_done", "session_id": sid, "data": {"id": task_id, "session_id": sid, "status": "DONE", "final_path": out_mp3}})
        except Exception as e:
            update_task(task_id, error_log=f"Lỗi tách MP3: {str(e)[:200]}")
            broadcast_sync({"event": "task_error", "session_id": sid, "data": {"id": task_id, "session_id": sid, "error": str(e)[:200]}})

    bg_tasks.add_task(run_audio)
    return {"status": "audio_extracting_started"}


@app.post("/api/tasks/{task_id}/compress")
async def api_compress_task(task_id: int, bg_tasks: BackgroundTasks):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    src_path = task.get("raw_path") or task.get("final_path")
    if not src_path or not os.path.exists(src_path):
        raise HTTPException(status_code=400, detail="Tệp gốc không tồn tại để nén")
    sid = task.get("session_id", "default")

    def run_comp():
        try:
            update_task(task_id, speed="Đang nén", progress=50.0)
            comp_path = os.path.join(PROCESSED_DIR, f"compressed_{task_id}.mp4")
            compress_video(src_path, output_path=comp_path)
            update_task(task_id, speed="Đã nén", progress=100.0)
            broadcast_sync({"event": "task_done", "session_id": sid, "data": {"id": task_id, "session_id": sid, "status": "DONE", "final_path": comp_path}})
        except Exception as e:
            update_task(task_id, error_log=f"Lỗi nén: {str(e)[:150]}")
            broadcast_sync({"event": "task_error", "session_id": sid, "data": {"id": task_id, "session_id": sid, "error": str(e)[:150]}})

    bg_tasks.add_task(run_comp)
    return {"status": "compressing_started"}


@app.post("/api/ai/autocaptions")
async def api_autocaptions(req: AutoCaptionRequest, bg_tasks: BackgroundTasks):
    task = get_task(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    src_path = task.get("raw_path") or task.get("final_path")
    if not src_path or not os.path.exists(src_path):
        raise HTTPException(status_code=400, detail="Không tìm thấy tệp video để tạo phụ đề")
    sid = task.get("session_id", "default")

    def run_captions():
        try:
            update_task(req.task_id, speed="AI Phụ Đề", progress=30.0)
            broadcast_sync({"event": "task_progress", "session_id": sid, "data": {"id": req.task_id, "session_id": sid, "progress": 30.0, "speed": "AI Phụ Đề"}})
            out_cap = os.path.join(PROCESSED_DIR, f"captioned_{req.task_id}.mp4")
            apply_ai_autocaptions(
                video_path=src_path,
                output_path=out_cap,
                style_preset=req.style_preset or "capcut_yellow",
                position=req.position or "bottom",
                skip_if_exists=bool(req.skip_if_exists)
            )
            update_task(req.task_id, final_path=out_cap, speed="Đã tạo phụ đề", progress=100.0, status="READY")
            broadcast_sync({"event": "task_done", "session_id": sid, "data": {"id": req.task_id, "session_id": sid, "status": "READY", "final_path": out_cap}})
        except Exception as e:
            update_task(req.task_id, error_log=f"Lỗi tạo phụ đề: {str(e)[:150]}")
            broadcast_sync({"event": "task_error", "session_id": sid, "data": {"id": req.task_id, "session_id": sid, "error": str(e)[:150]}})

    bg_tasks.add_task(run_captions)
    return {"status": "autocaptions_started"}


@app.post("/api/ai/dubbing")
async def api_dubbing(req: VoiceoverDubbingRequest, bg_tasks: BackgroundTasks):
    task = get_task(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    src_path = task.get("raw_path") or task.get("final_path")
    if not src_path or not os.path.exists(src_path):
        raise HTTPException(status_code=400, detail="Không tìm thấy tệp video để lồng tiếng")
    sid = task.get("session_id", "default")

    def run_dub():
        try:
            update_task(req.task_id, speed="AI Lồng Tiếng", progress=30.0)
            broadcast_sync({"event": "task_progress", "session_id": sid, "data": {"id": req.task_id, "session_id": sid, "progress": 30.0, "speed": "AI Lồng Tiếng"}})
            out_dub = os.path.join(PROCESSED_DIR, f"dubbed_{req.task_id}.mp4")
            apply_ai_voiceover_dubbing(
                video_path=src_path,
                output_path=out_dub,
                voice_type=req.voice_type or "male_north"
            )
            update_task(req.task_id, final_path=out_dub, speed="Đã lồng tiếng", progress=100.0, status="READY")
            broadcast_sync({"event": "task_done", "session_id": sid, "data": {"id": req.task_id, "session_id": sid, "status": "READY", "final_path": out_dub}})
        except Exception as e:
            update_task(req.task_id, error_log=f"Lỗi lồng tiếng: {str(e)[:150]}")
            broadcast_sync({"event": "task_error", "session_id": sid, "data": {"id": req.task_id, "session_id": sid, "error": str(e)[:150]}})

    bg_tasks.add_task(run_dub)
    return {"status": "dubbing_started"}


@app.post("/api/ai/highlights")
async def api_highlights(req: HighlightsRequest):
    task = get_task(req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    src_path = task.get("raw_path") or task.get("final_path")
    if not src_path or not os.path.exists(src_path):
        raise HTTPException(status_code=400, detail="Không tìm thấy tệp video để cắt Highlights")

    try:
        data = extract_smart_viral_clips(
            video_path=src_path,
            task_id=req.task_id,
            num_clips=req.num_clips or 3,
            clip_duration=req.clip_duration or 45,
            crop_mode=req.crop_mode or "blur"
        )
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi cắt Highlights: {str(e)[:200]}")


@app.get("/api/highlights/{task_id}/clip/{clip_num}")
async def api_download_highlight_clip(task_id: int, clip_num: int):
    clip_filename = f"highlight_{task_id}_clip_{clip_num}.mp4"
    clip_path = os.path.join(PROCESSED_DIR, clip_filename)
    if not os.path.exists(clip_path):
        raise HTTPException(status_code=404, detail="Clip không tồn tại hoặc chưa được cắt")
    return FileResponse(path=clip_path, filename=clip_filename, media_type="video/mp4")


@app.get("/api/highlights/{task_id}/zip")
async def api_download_highlight_zip(task_id: int):
    zip_filename = f"viral_highlights_{task_id}.zip"
    zip_path = os.path.join(PROCESSED_DIR, zip_filename)
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Gói ZIP không tồn tại hoặc chưa được tạo")
    return FileResponse(path=zip_path, filename=zip_filename, media_type="application/zip")




@app.get("/api/download/{task_id}")
async def api_download_file(task_id: int, type: Optional[str] = None):
    """
    Tải trực tiếp tệp về điện thoại hoặc máy tính cá nhân.
    Hỗ trợ các tùy chọn linh hoạt cho người dùng điện thoại:
    - type='clean' hoặc 'raw': Tải video gốc đã xóa sạch logo watermark
    - type='processed': Tải video đã lách bản quyền 9:16 (tự động render nếu chưa có)
    - type='audio': Tải file âm thanh MP3 320kbps (tự động trích xuất nếu chưa có)
    - type=None: Tải bản hoàn chỉnh hiện có
    """
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")

    target_path = None
    title = sanitize_filename(task.get("title") or f"video_{task_id}")

    if type == "audio":
        # Tìm file mp3 đã tách
        mp3_path = os.path.join(AUDIOS_DIR, f"{title}_{task_id}.mp3")
        clean_mp3 = os.path.join(AUDIOS_DIR, f"clean_{task_id}.mp3")

        if os.path.exists(mp3_path):
            target_path = mp3_path
        elif os.path.exists(clean_mp3):
            target_path = clean_mp3
        elif task.get("final_path") and task["final_path"].endswith(".mp3") and os.path.exists(task["final_path"]):
            target_path = task["final_path"]
        else:
            src_path = task.get("final_path") or task.get("raw_path")
            if src_path and os.path.exists(src_path):
                try:
                    target_path = extract_audio_mp3(src_path, output_path=mp3_path)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Lỗi tách MP3: {str(e)[:150]}")
            else:
                raise HTTPException(status_code=404, detail="Không tìm thấy file nguồn để tách nhạc")

    elif type == "processed":
        # Video đã lách bản quyền 9:16
        proc_path = os.path.join(PROCESSED_DIR, f"clean_{task_id}.mp4")
        if os.path.exists(proc_path):
            target_path = proc_path
        elif task.get("final_path") and os.path.exists(task["final_path"]) and "clean_" in task["final_path"]:
            target_path = task["final_path"]
        else:
            # Chưa lách, render nhanh
            src_path = task.get("raw_path") or task.get("final_path")
            if src_path and os.path.exists(src_path):
                try:
                    apply_anti_duplicate_filter(
                        input_path=src_path,
                        output_path=proc_path,
                        target_resolution=get_setting("target_resolution", "1080x1920"),
                        speed_factor=float(get_setting("speed_factor", 1.02)),
                        zoom_factor=float(get_setting("zoom_factor", 1.02)),
                        blur_background=bool(get_setting("blur_background", True))
                    )
                    update_task(task_id, final_path=proc_path, status="READY")
                    target_path = proc_path
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Lỗi lách bản quyền: {str(e)[:150]}")
            else:
                raise HTTPException(status_code=404, detail="Không tìm thấy file nguồn để xử lý")

    elif type == "compressed":
        # Video nén siêu nhẹ tối ưu di động / Zalo
        comp_path = os.path.join(PROCESSED_DIR, f"compressed_{task_id}.mp4")
        if os.path.exists(comp_path):
            target_path = comp_path
        else:
            src_path = task.get("raw_path") or task.get("final_path")
            if src_path and os.path.exists(src_path):
                try:
                    target_path = compress_video(src_path, output_path=comp_path)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Lỗi nén video: {str(e)[:150]}")
            else:
                raise HTTPException(status_code=404, detail="Không tìm thấy file nguồn để nén")

    elif type == "captioned":
        cap_path = os.path.join(PROCESSED_DIR, f"captioned_{task_id}.mp4")
        if os.path.exists(cap_path):
            target_path = cap_path
        else:
            src_path = task.get("raw_path") or task.get("final_path")
            if src_path and os.path.exists(src_path):
                try:
                    target_path = apply_ai_autocaptions(src_path, output_path=cap_path)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Lỗi tạo phụ đề: {str(e)[:150]}")
            else:
                raise HTTPException(status_code=404, detail="Không tìm thấy file nguồn để tạo phụ đề")

    elif type == "dubbed":
        dub_path = os.path.join(PROCESSED_DIR, f"dubbed_{task_id}.mp4")
        if os.path.exists(dub_path):
            target_path = dub_path
        else:
            src_path = task.get("raw_path") or task.get("final_path")
            if src_path and os.path.exists(src_path):
                try:
                    target_path = apply_ai_voiceover_dubbing(src_path, output_path=dub_path)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Lỗi lồng tiếng: {str(e)[:150]}")
            else:
                raise HTTPException(status_code=404, detail="Không tìm thấy file nguồn để lồng tiếng")

    elif type in ("clean", "raw"):
        # Video sạch gốc không logo
        target_path = task.get("raw_path") or task.get("final_path")
    else:
        # Mặc định lấy final_path hoặc raw_path
        target_path = task.get("final_path") or task.get("raw_path")

    if not target_path or not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="Tệp không tồn tại trên hệ thống")

    filename = os.path.basename(target_path)
    return FileResponse(
        path=target_path,
        filename=filename,
        media_type="application/octet-stream"
    )


@app.get("/api/stats")
async def api_get_stats(session_id: Optional[str] = None):
    return get_stats(session_id=session_id)


@app.get("/api/tunnel")
async def api_get_tunnel():
    from core.tunnel import get_public_tunnel_url
    return {"public_url": get_public_tunnel_url()}


@app.get("/api/settings")
async def api_get_settings():
    return get_all_settings()


@app.post("/api/settings")
async def api_save_settings(req: SettingsRequest):
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            set_setting(k, v)
    if "max_concurrent_downloads" in data:
        try:
            new_workers = int(data["max_concurrent_downloads"])
            task_worker.stop()
            time.sleep(0.5)
            task_worker.start(num_workers=new_workers)
        except Exception:
            pass
    broadcast_sync({"event": "settings_updated", "data": data})
    return {"status": "success", "settings": get_all_settings()}


@app.post("/api/login-session")
async def api_trigger_login(bg_tasks: BackgroundTasks):
    """Kích hoạt mở trình duyệt để người dùng đăng nhập tài khoản một lần"""
    from core.reup_engine import run_login_session
    bg_tasks.add_task(run_login_session)
    return {"status": "success", "message": "Đang mở trình duyệt đăng nhập..."}


@app.post("/api/open-folder")
async def api_open_folder(req: OpenFolderRequest):
    folder = DOWNLOADS_DIR
    if req.type == "videos":
        folder = VIDEOS_DIR
    elif req.type == "audios":
        folder = AUDIOS_DIR
    elif req.type == "processed":
        folder = PROCESSED_DIR
    elif req.path:
        folder = req.path

    success = open_folder_in_explorer(folder)
    return {"status": "success" if success else "error", "path": folder}


def stream_file_with_range(path: str, range_header: Optional[str] = None):
    """
    Phát trực tuyến video/audio hỗ trợ chuẩn HTTP 206 Partial Content (Byte-Range requests).
    Đây là tiêu chuẩn bắt buộc của iOS Safari (iPhone / iPad / Mac) để xem trước video mượt mà.
    """
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Tệp không tồn tại")

    file_size = os.path.getsize(path)
    content_type = mimetypes.guess_type(path)[0] or "video/mp4"

    if range_header:
        # Xử lý dải byte yêu cầu từ Safari e.g. "bytes=0-1" hoặc "bytes=0-"
        try:
            h_range = range_header.strip()
            if h_range.startswith("bytes="):
                h_range = h_range[6:]
            parts = h_range.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
        except Exception:
            start = 0
            end = file_size - 1

        if start >= file_size:
            start = max(0, file_size - 1)
        if end >= file_size:
            end = file_size - 1
        if end < start:
            end = start

        chunk_length = (end - start) + 1

        def range_generator():
            with open(path, "rb") as f:
                f.seek(start)
                left = chunk_length
                while left > 0:
                    read_size = min(left, 1024 * 512)
                    chunk = f.read(read_size)
                    if not chunk:
                        break
                    left -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_length),
            "Content-Type": content_type,
        }
        return StreamingResponse(range_generator(), status_code=206, headers=headers)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": content_type,
    }

    def full_generator():
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 512):
                yield chunk

    return StreamingResponse(full_generator(), status_code=200, headers=headers)


@app.get("/media/stream/{task_id}")
async def api_media_stream_by_id(task_id: int, range: Optional[str] = Header(None)):
    """Phát video trực tiếp qua ID tác vụ cho iPhone / Android"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    path = task.get("final_path") or task.get("raw_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Tệp video không tồn tại")
    return stream_file_with_range(path, range)


@app.get("/media/preview")
async def api_media_preview(path: str, range: Optional[str] = Header(None)):
    """Xem trước video hoặc audio trực tiếp trên trình duyệt (hỗ trợ Safari)"""
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Tệp không tồn tại")
    return stream_file_with_range(path, range)
