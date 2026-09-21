@echo off
title Facebook Reels Auto-Uploader Bot
chcp 65001 > nul
cd /d "%~dp0"

echo ===================================================================
echo     🤖 Facebook Reels Auto-Uploader Bot (China AI Movie)
echo ===================================================================
echo.
echo  [+] กำลังเริ่มต้นระบบ และ เปิดหน้าต่างโปรแกรม...
echo.

python run.py

if %errorlevel% neq 0 (
    echo.
    echo [!] เกิดข้อผิดพลาดในการเปิดโปรแกรม
    echo กรุณาตรวจสอบข้อความ Error ด้านบน
    echo.
    pause
)
