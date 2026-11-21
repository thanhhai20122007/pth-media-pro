@echo off
chcp 65001 >nul
title PTH Media Pro - Hệ Thống Tải & Xử Lý Video Đa Nền Tảng
cd /d "%~dp0"
echo ======================================================================
echo       🚀 KHỞI ĐỘNG HỆ THỐNG PTH MEDIA PRO V2.5
echo ======================================================================
python main.py --mode web
pause
