@echo off
chcp 65001 > nul
title Reels Bot - Standalone Web Server
echo ========================================================
echo   ⚡ Starting Reels Bot Web Server (Port 5555)...
echo   📱 Mobile Dashboard: http://localhost:5555
echo ========================================================
python web_server.py
pause
