# ==========================================================================
#  ONE-TIME: register the cloud backup as a Windows Scheduled Task — hourly
#  during working hours (06:00-20:00) then every 3h overnight — with automatic
#  CATCH-UP so a missed window is never silently lost.
#
#  Run this ONCE on the backup PC, in an ADMIN PowerShell:
#      powershell -ExecutionPolicy Bypass -File .\setup-backup-schedule.ps1
#
#  What it guarantees (your requirement: "if the 19:00 backup did not happen
#  because the PC was off, it must run as soon as the PC is back — before more
#  data entry piles up"):
#    - StartWhenAvailable  -> if the PC was OFF at a scheduled time (e.g. 19:00),
#                             the MISSED run fires the moment the PC is next
#                             turned on — it is caught up, never skipped.
#    - Restart on failure  -> if the run STARTED but the internet was down,
#                             it retries every 15 min (up to 5x) until it works.
#    - local-backup.ps1 itself also retries pg_dump 5x/60s within a run.
#  Together: every window is caught up automatically, no manual step.
# ==========================================================================

$ErrorActionPreference = "Stop"

# Full path to local-backup.ps1 (assumed to sit next to THIS script).
$ScriptPath = Join-Path $PSScriptRoot "local-backup.ps1"
if (-not (Test-Path $ScriptPath)) { throw "local-backup.ps1 not found next to this script: $ScriptPath" }

$TaskName = "ASW Cloud Backup"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$ScriptPath`""

# Sync EVERY HOUR during working hours (06:00-20:00), then EVERY 3 HOURS
# overnight (23:00, 02:00, 05:00) so the cloud/mobile stays close to live all
# day and still refreshes a few times overnight. A missed run (PC off) is
# caught up on next boot. Adjust the hour list if your hours change.
$hours = @(6,7,8,9,10,11,12,13,14,15,16,17,18,19,20, 23, 2, 5)
$triggers = foreach ($h in $hours) {
    New-ScheduledTaskTrigger -Daily -At ([datetime]::Today).AddHours($h)
}

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 15) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries

# Run as SYSTEM so it works "whether logged on or not" without storing a
# Windows password. SYSTEM uses the machine PATH, so PostgreSQL and the AWS CLI
# must be installed for "all users" (their default installers do this).
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' (hourly 06:00-20:00, then 23:00/02:00/05:00; catch-up + retry)."
Write-Host "Test it now with:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Then check D:\ASW-Backups for a new .dump and open the local 'timber' db in pgAdmin."
