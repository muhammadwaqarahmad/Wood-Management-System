# ==========================================================================
#  Run the app from SOURCE against the LOCAL PostgreSQL — the fast test loop.
#  (No 15-minute exe rebuild needed; this runs the current code directly.)
#
#      powershell -ExecutionPolicy Bypass -File .\run-local.ps1
#
#  It starts the local PostgreSQL first if it isn't running (it's a portable
#  install, so it stops when the PC sleeps/reboots).
# ==========================================================================

# 1) make sure the local database is up
if (-not (Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue)) {
    Write-Host "Local PostgreSQL is down - starting it..." -ForegroundColor Yellow
    & "E:\pglocal\pgsql\bin\pg_ctl.exe" -D "E:\pglocal\data" -l "E:\pglocal\pg.log" -o "-p 5432" start
    Start-Sleep -Seconds 4
}
if (Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "PostgreSQL: UP (127.0.0.1:5432)" -ForegroundColor Green
} else {
    Write-Host "PostgreSQL did NOT start - the app will lag/reconnect. Check E:\pglocal\pg.log" -ForegroundColor Red
}

# 2) point the app at the local database
$env:TIMBER_DB_BACKEND = "postgresql"
$env:TIMBER_PG_HOST    = "127.0.0.1"
$env:TIMBER_PG_PORT    = "5432"
$env:TIMBER_PG_USER    = "timber"
$env:TIMBER_PG_PASSWORD= "WaqarPass123"
$env:TIMBER_PG_DB      = "timber"
$env:TIMBER_LANG       = "ur"
# Set TIMBER_FORCE_GPU=0 here if the forced-GPU rendering ever looks broken.

# 3) clear a stale single-instance lock left by a force-killed run
Remove-Item (Join-Path $PSScriptRoot "storage\app.lock") -Force -ErrorAction SilentlyContinue

Write-Host "Launching app from source..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") -m timber.app
