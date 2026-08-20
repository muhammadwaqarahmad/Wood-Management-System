# Serve the FAST production build of the website (not the slow `npm run dev`).
# Run desktop\run-api.ps1 first (the API), then this.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not $env:API_PROXY_TARGET) { $env:API_PROXY_TARGET = "http://127.0.0.1:8000" }
if (-not (Test-Path ".next\BUILD_ID")) {
  Write-Host "Building the website for the first time..."
  npm run build
}
Write-Host "Starting the website on http://127.0.0.1:3000"
npm run start
