@echo off
title Push PTH Media Pro to GitHub
cd /d "%~dp0"
echo =======================================================
echo          PUSH PTH MEDIA PRO TO GITHUB
echo =======================================================
echo.
git remote remove origin 2>nul
git remote add origin https://github.com/thanhhai20122007/pth-media-pro.git
git branch -M main
echo Dang day ma nguon len GitHub thanhhai20122007/pth-media-pro...
echo (Neu co cua so trinh duyet hien ra, ban chi can bam 'Sign in with browser' de xac nhan)
echo.
git push -u origin main
echo.
if %errorlevel% equ 0 (
    echo [THANH CONG] Da day ma nguon len GitHub thanh cong!
) else (
    echo [LUA CHON 2] Neu bi loi quyen truy cap, ban chi can:
    echo 1. Vao trang web GitHub tren man hinh
    echo 2. Bam vao nut 'Invite collaborators'
    echo 3. Nhap: pthaiii8386-debug va them vao
    echo 4. Chay lai file nay!
)
echo =======================================================
pause
