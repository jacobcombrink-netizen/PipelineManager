@echo off
title Pipeline Manager
echo.
echo  ============================================
echo   Pipeline Manager v0.4
echo  ============================================
echo.

:: Stay in the script's own directory no matter where it's launched from
cd /d "%~dp0"

:: Kill stale process on port 5000 (ignore errors if nothing is found)
echo  Clearing port 5000...
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| find "0.0.0.0:5000"') do taskkill /PID %%P /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| find "127.0.0.1:5000"') do taskkill /PID %%P /F >nul 2>&1

:: Remove cached bytecode
if exist __pycache__ rmdir /s /q __pycache__

echo  Starting server...
echo.
echo       http://localhost:5000
echo.
echo  Keep this window open while using the app.
echo  Close it or press Ctrl+C to stop.
echo  ============================================
echo.

python app.py

echo.
echo  Server stopped.
pause
