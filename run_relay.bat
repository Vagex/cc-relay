@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

echo ============================================
echo Starting Codex Web Relay...
echo Working directory: %CD%
echo ============================================
python codex_web_relay.py

echo.
echo ============================================
echo Relay process exited. Press any key to close.
echo ============================================
pause >nul
