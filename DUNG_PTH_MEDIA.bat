@echo off
chcp 65001 >nul
title Dừng Hệ Thống PTH Media Pro
cd /d "%~dp0"
echo ==========================================================
echo       🛑 ĐANG DỪNG HỆ THỐNG PTH MEDIA PRO...
echo ==========================================================
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
    echo [+] Đã dừng tiến trình Web Server ngầm (PID %%a)
)
taskkill /f /im cloudflared.exe >nul 2>&1
echo.
echo ✅ Đã dừng toàn bộ dịch vụ PTH Media Pro thành công!
echo ==========================================================
timeout /t 3 >nul
