@echo off
chcp 65001 >nul
title PTH MEDIA PRO - HỆ THỐNG TẢI & XỬ LÝ VIDEO ĐA NỀN TẢNG
cls
echo ======================================================================
echo           🚀 PTH MEDIA PRO - HỆ THỐNG TẢI & XỬ LÝ VIDEO V2.5
echo      Tải Video Sạch Không Logo (TikTok, Douyin, FB, YT, Insta, Threads, X)
echo          Tải Đa Luồng Song Song • Lách Bản Quyền FFmpeg 9:16
echo ======================================================================
echo.
echo [1] Chạy Giao Diện Web Trực Tiếp (Có cửa sổ đen CMD)
echo [2] Chạy ẨN HOÀN TOÀN NGẦM (Không hiện CMD, tắt máy tính terminal vẫn chạy)
echo [3] Mở Giao Diện Cửa Sổ Desktop App (Window)
echo [4] Chạy Chế Độ Tự Động Reup Đa Kênh (TikTok, Facebook, Threads)
echo [5] Đăng Nhập Tài Khoản Để Lưu Cookie (TikTok, FB, Threads, Insta)
echo [6] Xem Bảng Tiến Độ Tải (--status)
echo [7] Mở Thư Mục Chứa Video Đã Tải Về
echo [8] DỪNG HỆ THỐNG (Tắt dịch vụ chạy ngầm)
echo.
set /p choice="Nhập lựa chọn của bạn (1-8): "

if "%choice%"=="1" (
    echo Đang khởi chạy giao diện Web...
    python main.py --mode web
) else if "%choice%"=="2" (
    echo Đang kích hoạt chế độ chạy ngầm ẩn 100%...
    wscript.exe CHAY_NGAM_PTH_MEDIA.vbs
    echo.
    echo ✅ PTH Media Pro đã chạy ngầm trong Windows!
    echo Bây giờ bạn có thể tắt cửa sổ này thoải mái.
    echo Mở trên điện thoại cùng Wi-Fi: http://192.168.1.10:5000
    timeout /t 5
) else if "%choice%"=="3" (
    echo Đang khởi chạy cửa sổ ứng dụng Desktop...
    python main.py --mode gui
) else if "%choice%"=="4" (
    echo Đang chạy chế độ Auto Reup...
    python auto_reup_pro.py
) else if "%choice%"=="5" (
    echo Đang mở trình duyệt đăng nhập...
    python auto_reup_pro.py --login
) else if "%choice%"=="6" (
    python main.py --status
    pause
) else if "%choice%"=="7" (
    python main.py --open-dir
) else if "%choice%"=="8" (
    call DUNG_PTH_MEDIA.bat
) else (
    echo Lựa chọn mặc định: Khởi động giao diện Web...
    python main.py --mode web
)
