@echo off
echo ============================================
echo  Pipeline Manager - First-Time Setup
echo ============================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to tick "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Python found. Installing dependencies...
python -m pip install --upgrade pip
python -m pip install flask

echo.
echo ============================================
echo  Setup complete!
echo  Double-click run.bat to start the app.
echo ============================================
pause
