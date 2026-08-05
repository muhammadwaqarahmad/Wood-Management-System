# One-time setup for the Flutter app.
#
# `flutter create` generates the native iPhone + Android project folders, but it
# also overwrites pubspec.yaml and lib/main.dart with its starter templates.
# This script preserves OUR app code around that step.
#
#   Run in an ADMIN-not-required PowerShell:  .\setup.ps1

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

Write-Host "1/4  Backing up app code..."
Copy-Item "$here\lib" "$here\.keep_lib" -Recurse -Force
Copy-Item "$here\pubspec.yaml" "$here\.keep_pubspec.yaml" -Force

Write-Host "2/4  Generating native iOS + Android projects..."
flutter create --org com.abdulsattarwoods --project-name asw_mobile .

Write-Host "3/4  Restoring app code over the templates..."
Copy-Item "$here\.keep_lib\*" "$here\lib" -Recurse -Force
Copy-Item "$here\.keep_pubspec.yaml" "$here\pubspec.yaml" -Force
Remove-Item "$here\.keep_lib" -Recurse -Force
Remove-Item "$here\.keep_pubspec.yaml" -Force

Write-Host "4/4  Fetching dependencies..."
flutter pub get

Write-Host ""
Write-Host "Done. Next:"
Write-Host "  1. Start the API on the server:   python -m timber.api"
Write-Host "  2. Check mobile/lib/config.dart points at the server IP"
Write-Host "  3. Run the app:                    flutter run"
