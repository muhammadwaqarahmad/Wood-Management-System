@echo off
REM ==========================================================================
REM  Speed up "Abdul Sattar Woods"
REM
REM  Tells Windows Defender to TRUST this app's folder, so it stops re-scanning
REM  ~160 MB of program files every single time the app opens. That scan is the
REM  main reason the app is slow to start (10-30s); after this it opens in a few
REM  seconds.
REM
REM  Run this ONCE per PC. It will ask for administrator permission (needed to
REM  change a Windows Defender setting). Nothing else is changed.
REM ==========================================================================

REM --- make sure we are running as administrator; if not, re-launch elevated ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Asking for administrator permission...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

REM --- the folder this .bat sits in = the app's install folder ---
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"

echo.
echo Trusting this folder in Windows Defender:
echo   %APPDIR%
echo.

powershell -NoProfile -Command "Add-MpPreference -ExclusionPath '%APPDIR%'"

if %errorlevel% equ 0 (
    echo Done. "Abdul Sattar Woods" will now open faster.
) else (
    echo Something went wrong. Please tell your software provider.
)
echo.
pause
