@echo off
title Pipeline Manager - Debug Mode
cd /d "%~dp0"
echo Current directory: %CD%
echo.
echo Checking Python...
python --version
echo.
echo Checking app.py exists...
if exist app.py (echo   app.py found) else (echo   ERROR: app.py NOT found!)
echo.
echo Starting with full error output...
echo ============================================
echo.
python app.py
echo.
echo ============================================
echo  If you see an error above, screenshot it
echo  and share it for debugging.
echo ============================================
pause
