@echo off
chcp 65001 >nul
title Login Gemini (mahaxok.83@gmail.com)
echo ========================================================
echo   GEMINI WEB ONE-TIME LOGIN (Google Account)
echo   Target: mahaxok.83@gmail.com
echo ========================================================
echo.

set "PY_EXE=C:\Users\kee_n\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY_EXE%" (
    set "PY_EXE=python"
)

"%PY_EXE%" "Z:\Projects\Page Reel uplaod 2\core\gemini_web_poster.py" --login --email mahaxok.83@gmail.com
echo.
pause
