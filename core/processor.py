import os
import subprocess
import time
from typing import Dict, Any, Optional, Callable
from core.config import (
    FFMPEG_EXE,
    PROCESSED_DIR,
    AUDIOS_DIR,
    LOGO_PATH,
)


def get_video_info(input_path: str) -> Dict[str, Any]:
    """Lấy thông tin độ phân giải, thời lượng của video bằng ffprobe"""
    bin_dir = os.path.dirname(FFMPEG_EXE)
    ffprobe = os.path.join(bin_dir, "ffprobe.exe")
    if not os.path.exists(ffprobe):
        ffprobe = "ffprobe"

    cmd = [
        ffprobe,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = res.stdout.strip().splitlines()
        w = int(lines[0]) if len(lines) > 0 and lines[0].isdigit() else 1080
        h = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else 1920
        d = float(lines[2]) if len(lines) > 2 else 0.0
        return {"width": w, "height": h, "duration": d}
    except Exception:
        return {"width": 1080, "height": 1920, "duration": 0.0}


def apply_anti_duplicate_filter(
    input_path: str,
    output_path: str,
    target_resolution: str = "1080x1920",
    speed_factor: float = 1.02,
    zoom_factor: float = 1.02,
    blur_background: bool = True,
    watermark_path: Optional[str] = None,
    watermark_position: str = "top_right",
    watermark_opacity: float = 0.85,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    Bộ xử lý FFmpeg chống quét trùng lặp / lách bản quyền:
    - Chuẩn hóa khung hình dọc 1080x1920 (Nền mờ nghệ thuật hoặc Nền đen)
    - Zoom nhẹ 2% và crop để đổi ma trận điểm ảnh
    - Đổi nhẹ tốc độ 1.02x để đổi mã băm sóng âm & hình ảnh
    - Xóa sạch toàn bộ thông tin siêu dữ liệu (Metadata) cũ
    - Đóng dấu logo thương hiệu cá nhân nếu có
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {input_path}")

    # Tính toán PTS cho hình ảnh và atempo cho âm thanh
    pts_factor = round(1.0 / speed_factor, 4)
    atempo = round(speed_factor, 4)

    # Vị trí logo overlay
    wm_positions = {
        "top_right": "W-w-30:30",
        "top_left": "30:30",
        "bottom_right": "W-w-30:H-h-30",
        "bottom_left": "30:H-h-30",
    }
    wm_pos_str = wm_positions.get(watermark_position, "W-w-30:30")

    has_watermark = watermark_path and os.path.exists(watermark_path)
    if not has_watermark and os.path.exists(LOGO_PATH):
        watermark_path = LOGO_PATH
        has_watermark = True

    if target_resolution == "1080x1920":
        if blur_background:
            # Hiệu ứng nền mờ (Blurred Background) chuyên nghiệp cho video ngang/vuông thành 9:16
            filter_complex = (
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2[merged];"
                f"[merged]scale=1102:1958,crop=1080:1920,setpts={pts_factor}*PTS[v_out]"
            )
        else:
            # Viền đen cân đối
            filter_complex = (
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
                f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
                f"scale=1102:1958,crop=1080:1920,setpts={pts_factor}*PTS[v_out]"
            )
    else:
        # Giữ nguyên tỉ lệ gốc, chỉ zoom nhẹ 2%
        filter_complex = (
            f"[0:v]scale=iw*{zoom_factor}:ih*{zoom_factor},"
            f"crop=iw/{zoom_factor}:ih/{zoom_factor},"
            f"setpts={pts_factor}*PTS[v_out]"
        )

    # Thêm chèn watermark nếu có
    if has_watermark:
        cmd = [
            FFMPEG_EXE, "-y",
            "-i", input_path,
            "-i", watermark_path,
            "-filter_complex",
            f"{filter_complex};[1:v]scale=180:-1,format=rgba,colorchannelmixer=aa={watermark_opacity}[wm];[v_out][wm]overlay={wm_pos_str}",
            "-af", f"atempo={atempo},equalizer=f=1000:t=q:w=1:g=0.3",
            "-map_metadata", "-1",
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path
        ]
    else:
        cmd = [
            FFMPEG_EXE, "-y",
            "-i", input_path,
            "-filter_complex", filter_complex,
            "-map", "[v_out]",
            "-map", "0:a?",
            "-af", f"atempo={atempo},equalizer=f=1000:t=q:w=1:g=0.3",
            "-map_metadata", "-1",
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path
        ]

    if progress_callback:
        progress_callback(10.0, "Đang khởi tạo FFmpeg...")

    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if process.returncode != 0:
        err_msg = process.stderr[-300:] if process.stderr else "Lỗi không xác định khi render"
        raise Exception(f"FFmpeg thất bại: {err_msg}")

    if progress_callback:
        progress_callback(100.0, "Hoàn tất render")

    return output_path


def extract_audio_mp3(input_path: str, output_path: Optional[str] = None) -> str:
    """Tách âm thanh từ video sang định dạng MP3 320kbps chất lượng cao nhất"""
    if not output_path:
        base = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(AUDIOS_DIR, f"{base}.mp3")

    cmd = [
        FFMPEG_EXE, "-y",
        "-i", input_path,
        "-vn",
        "-c:a", "libmp3lame",
        "-b:a", "320k",
        "-map_metadata", "-1",
        output_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def compress_video(
    input_path: str,
    output_path: Optional[str] = None,
    crf: int = 28,
    target_height: int = 720,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    Bộ nén video thông minh siêu nhẹ (Smart Video Compression):
    - Tối ưu cho thiết bị di động, chia sẻ qua Zalo, Messenger, Telegram
    - Giảm 50% - 75% dung lượng tệp tin mà vẫn giữ độ nét sắc sảo trên màn hình điện thoại
    - Hạn chế chiều cao tối đa target_height (mặc định 720p), H.264 CRF 28, preset faster, AAC 96k, +faststart
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Không tìm thấy file nguồn để nén: {input_path}")

    if not output_path:
        base = os.path.splitext(os.path.basename(input_path))[0]
        output_path = os.path.join(PROCESSED_DIR, f"compressed_{base}.mp4")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Co tỉ lệ nếu chiều cao > target_height, đảm bảo kích thước chẵn
    vf_filter = f"scale='if(gt(ih,{target_height}),-2,iw)':'if(gt(ih,{target_height}),{target_height},-2)'"

    cmd = [
        FFMPEG_EXE, "-y",
        "-i", input_path,
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", str(crf),
        "-c:a", "aac",
        "-b:a", "96k",
        "-movflags", "+faststart",
        output_path
    ]

    if progress_callback:
        progress_callback(10.0, "Đang nén video...")

    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if process.returncode != 0:
        err_msg = process.stderr[-300:] if process.stderr else "Lỗi FFmpeg khi nén"
        raise Exception(f"Lỗi nén video: {err_msg}")

    if progress_callback:
        progress_callback(100.0, "Hoàn tất nén video")

    return output_path

