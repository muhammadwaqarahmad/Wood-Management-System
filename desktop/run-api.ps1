# Starts the shared API for local development. KEEP THIS WINDOW OPEN while you
# use the website. Run it from PowerShell:  .\run-api.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:TIMBER_DB_BACKEND = "sqlite"
$env:TIMBER_API_CORS = "*"
Write-Host "Abdul Sattar Woods API -> http://127.0.0.1:8000  (Ctrl+C to stop)" -ForegroundColor Green
& "$PSScriptRoot\..\.venv\Scripts\python.exe" -m uvicorn timber.api.main:app --host 127.0.0.1 --port 8000
