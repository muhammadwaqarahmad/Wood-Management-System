# ==========================================================================
#  ONE-TIME: register the FOUR-TIMES-DAILY cloud backup as a Windows Scheduled
#  Task with automatic CATCH-UP so a missed window is never silently lost.
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

# Four runs a day across office hours (8am-7pm): start of day, midday, mid-
# afternoon, and close-of-day. The 7pm one captures the full day before closing.
# A missed run (PC off) is caught up on next boot. Adjust if your hours change.
$t1 = New-ScheduledTaskTrigger -Daily -At  8:00AM
$t2 = New-ScheduledTaskTrigger -Daily -At 12:00PM
$t3 = New-ScheduledTaskTrigger -Daily -At  4:00PM
$t4 = New-ScheduledTaskTrigger -Daily -At  7:00PM

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

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $t1, $t2, $t3, $t4 `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' (08:00, 12:00, 16:00, 19:00; catch-up + retry)."
Write-Host "Test it now with:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Then check D:\ASW-Backups for a new .dump and open the local 'timber' db in pgAdmin."
