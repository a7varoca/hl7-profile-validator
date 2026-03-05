@echo off
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python not found. Download and install it from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo Creating virtual environment...
python -m venv .venv

echo Installing dependencies...
.venv\Scripts\pip install --no-cache-dir -r requirements.txt

echo.
echo Setup complete. Run start.bat to launch the application.
pause
