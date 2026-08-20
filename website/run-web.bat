@echo off
REM Serve the FAST production build of the website (not the slow `npm run dev`).
REM Run desktop\run-api.bat first (the API), then this.
cd /d "%~dp0"
if not defined API_PROXY_TARGET set API_PROXY_TARGET=http://127.0.0.1:8000
if not exist ".next\BUILD_ID" (
  echo Building the website for the first time...
  call npm run build
)
echo Starting the website on http://127.0.0.1:3000
call npm run start
