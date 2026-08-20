@echo off
REM Starts the shared API for local development. Double-click this file, or run
REM it from a terminal. KEEP THE WINDOW OPEN while you use the website.
cd /d "%~dp0"
set TIMBER_DB_BACKEND=sqlite
set TIMBER_API_CORS=*
echo Starting Abdul Sattar Woods API on http://127.0.0.1:8000
echo Keep this window OPEN. Press Ctrl+C to stop.
echo.
"%~dp0..\.venv\Scripts\python.exe" -m uvicorn timber.api.main:app --host 127.0.0.1 --port 8000
echo.
echo The API stopped. Press any key to close.
pause >nul
