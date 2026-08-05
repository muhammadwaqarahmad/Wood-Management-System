# Builds the release APK with the cloud API URL baked in as the DEFAULT,
# so nothing needs typing on each phone.
#
#   powershell -File deploy\cloud-api\build-cloud-apk.ps1 -Url https://asw-api.onrender.com
#
# Output: AbdulSattarWoods.apk in the project root.
param(
    [Parameter(Mandatory = $true)][string]$Url
)

$ErrorActionPreference = "Stop"
$env:JAVA_HOME = "C:\Users\User\asw-tools\jdk17\current"
$env:ANDROID_HOME = "C:\Users\User\asw-tools\android-sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:PATH = "$($env:JAVA_HOME)\bin;$($env:PATH)"

$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location "$root\mobile"

Write-Output "Building APK with API_URL = $Url ..."
& C:\src\flutter\bin\flutter.bat build apk --release --dart-define=API_URL=$Url
if ($LASTEXITCODE -ne 0) { throw "flutter build failed ($LASTEXITCODE)" }

Copy-Item "build\app\outputs\flutter-apk\app-release.apk" "$root\AbdulSattarWoods.apk" -Force
Write-Output "Done -> $root\AbdulSattarWoods.apk  (default server = $Url)"
