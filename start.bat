@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\uvicorn.exe" (
    echo Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

echo Starting HL7 Profile Validator at http://localhost:8000
start http://localhost:8000
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
