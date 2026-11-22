@echo off
chcp 65001 >nul
title PTH Media Pro - Siêu Trạm Tải Video (Super Node)
color 0A
echo =====================================================================
echo           PTH MEDIA PRO - TỰ ĐỘNG KẾT NỐI CLOUD VÀ MÁY TÍNH
echo =====================================================================
echo [*] Đang khởi động hệ thống tải đa năng...
echo [*] Bật máy tính để web pth-media-pro.onrender.com tải YouTube không chặn!
echo [*] Link cục bộ:  http://127.0.0.1:5000
echo [*] Link Cloud:   https://pth-media-pro.onrender.com
echo =====================================================================
echo.
python main.py --mode web
pause
