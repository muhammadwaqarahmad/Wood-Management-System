# ==========================================================================
#  BACKUP - runs on the server PC (local-primary architecture).
#  The LIVE database is the LOCAL PostgreSQL "timber". This script copies it
#  OFF the machine so nothing is lost if the PC dies:
#    1. pg_dump the LOCAL "timber" db            -> dated .dump file on THIS PC
#    2. upload that dump to Cloudflare R2         (off-site file copy)
#    3. push it INTO Supabase (overwrite)         (off-site DB backup + what the
#                                                  future mobile app reads)
#    4. keep the most recent N dump files locally, delete older ones
#
#  Steps 2-3 need the internet; if it's down they RETRY, and the scheduled task
#  (setup-backup-schedule.ps1) reruns when the PC/internet is back - so a missed
#  window is caught up. The LOCAL dump (step 1) always succeeds regardless.
#
#  Requirements on this PC:
#    - PostgreSQL  (pg_dump / pg_restore)  - already present (it runs the local DB).
#      This script AUTO-FINDS them in C:\Program Files\PostgreSQL\<ver>\bin even
#      if they are not on PATH (the SYSTEM scheduled task uses the machine PATH,
#      which usually does NOT include the PostgreSQL bin - that is the usual
#      "pg_dump is not installed" cause).
#    - AWS CLI     (R2 is S3-compatible)   - only needed if $UploadToR2 = $true.
#
#  QUICK DIAGNOSE (run this first, does NOT touch the database):
#      powershell -ExecutionPolicy Bypass -File .\local-backup.ps1 -Check
# ==========================================================================

param([switch]$Check)   # -Check = preflight only: verify tools + config, then exit.

# ---------- CONFIG - fill these in ----------------------------------------
# The LOCAL database (the live one, on this PC):
$LocalPgHost = "localhost"
$LocalPgPort = "5432"
$LocalPgUser = "timber"
$LocalPgDb   = "timber"
$LocalPgPassword = "PASTE-LOCAL-POSTGRES-PASSWORD-HERE"

# Where to keep the dump files on THIS pc. Change to C:\ASW-Backups if no D: drive.
$BackupDir   = "D:\ASW-Backups"

# --- Cloudflare R2 (off-site file copy). Set $UploadToR2=$false to skip. ---
$UploadToR2   = $true
$R2AccountId  = "<R2_ACCOUNT_ID>"                 # from the R2 dashboard
$R2Bucket     = "abdul-sattar-woods-backups"      # add a Lifecycle rule in R2: delete > 90 days
$env:AWS_ACCESS_KEY_ID     = "<R2_ACCESS_KEY_ID>"
$env:AWS_SECRET_ACCESS_KEY = "<R2_SECRET_KEY>"
$env:AWS_DEFAULT_REGION    = "auto"

# --- Supabase off-site DB backup (also the copy mobile reads). ---
# Set $PushToSupabase=$false if you only want R2 + local dumps for now.
$PushToSupabase = $true
$SupabaseUrl    = "postgresql://postgres.piqrfdwirbpbfcdibdmh:PASTE-DB-PASSWORD-HERE@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require"

# Keep the most recent N dump FILES locally. Twice a day => 60 files is ~30 days.
$KeepDumps   = 60
# --------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

# ---------- locate the PostgreSQL client tools + AWS CLI -------------------
# Prefer PATH; otherwise search the standard PostgreSQL install folders. This is
# what makes the SYSTEM scheduled task work without editing the machine PATH.
function Find-Tool {
    param([string]$Exe, [string[]]$Globs)
    $cmd = Get-Command $Exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($g in $Globs) {
        $hit = Get-ChildItem -Path $g -ErrorAction SilentlyContinue |
               Sort-Object FullName -Descending | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}
$pgDirs = @(
    "C:\Program Files\PostgreSQL\*\bin",
    "C:\Program Files (x86)\PostgreSQL\*\bin"
)
$PgDump    = Find-Tool "pg_dump.exe"    ($pgDirs | ForEach-Object { Join-Path $_ "pg_dump.exe" })
$PgRestore = Find-Tool "pg_restore.exe" ($pgDirs | ForEach-Object { Join-Path $_ "pg_restore.exe" })
$AwsCli    = Find-Tool "aws.exe"        @("C:\Program Files\Amazon\AWSCLIV2\aws.exe")

function Test-Placeholder([string]$v) { return ($v -match "PASTE|<.*>") }

# ---------- PREFLIGHT ------------------------------------------------------
$problems = @()
if (-not $PgDump)    { $problems += "pg_dump not found (install PostgreSQL client tools, or it is not in C:\Program Files\PostgreSQL\<ver>\bin)." }
if (-not $PgRestore) { $problems += "pg_restore not found (same PostgreSQL bin folder as pg_dump)." }
if (Test-Placeholder $LocalPgPassword) { $problems += "LocalPgPassword is still the PASTE-... placeholder - put the real local Postgres password in the CONFIG block." }
if ($UploadToR2) {
    if (-not $AwsCli) { $problems += "AWS CLI (aws.exe) not found but `$UploadToR2 = `$true - install AWS CLI v2, or set `$UploadToR2 = `$false." }
    if ((Test-Placeholder $R2AccountId) -or (Test-Placeholder $env:AWS_ACCESS_KEY_ID) -or (Test-Placeholder $env:AWS_SECRET_ACCESS_KEY)) {
        $problems += "R2 credentials (account id / access key / secret) still contain placeholders."
    }
}
if ($PushToSupabase -and (Test-Placeholder $SupabaseUrl)) {
    $problems += "SupabaseUrl still contains the PASTE-DB-PASSWORD placeholder."
}

Write-Host "---- preflight ----"
Write-Host ("  pg_dump    : " + ($(if ($PgDump)    { $PgDump }    else { "NOT FOUND" })))
Write-Host ("  pg_restore : " + ($(if ($PgRestore) { $PgRestore } else { "NOT FOUND" })))
Write-Host ("  aws        : " + ($(if ($AwsCli)    { $AwsCli }    else { "not found" + $(if ($UploadToR2) { " (REQUIRED - R2 enabled)" } else { " (ok - R2 disabled)" }) })))
Write-Host ("  R2 upload  : " + $UploadToR2)
Write-Host ("  Supabase   : " + $PushToSupabase)
if ($problems.Count -gt 0) {
    Write-Host ""
    Write-Warning "Setup is INCOMPLETE:"
    $problems | ForEach-Object { Write-Host "   - $_" -ForegroundColor Yellow }
    if ($Check) { exit 1 }
    throw "Fix the items above, then re-run. (Run with -Check to preview without touching the DB.)"
}
Write-Host "  preflight OK."
if ($Check) { Write-Host "-Check only: nothing was backed up."; exit 0 }

# ---------- RUN -----------------------------------------------------------
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$dump  = Join-Path $BackupDir "asw-$stamp.dump"
$env:PGPASSWORD = $LocalPgPassword

Write-Host "[1/4] Dumping LOCAL db '$LocalPgDb' -> $dump"
& $PgDump -h $LocalPgHost -p $LocalPgPort -U $LocalPgUser -d $LocalPgDb -Fc --no-owner --no-acl -f $dump
if ($LASTEXITCODE -ne 0) { throw "local pg_dump failed ($LASTEXITCODE)" }
Write-Host "      size: $([math]::Round((Get-Item $dump).Length/1MB,2)) MB  (this is the guaranteed backup)"

if ($UploadToR2) {
    Write-Host "[2/4] Uploading to Cloudflare R2 (retries if internet is down)"
    $done = $false
    for ($try = 1; $try -le 5 -and -not $done; $try++) {
        & $AwsCli s3 cp $dump "s3://$R2Bucket/daily/asw-$stamp.dump" `
            --endpoint-url "https://$R2AccountId.r2.cloudflarestorage.com"
        if ($LASTEXITCODE -eq 0) { $done = $true; Write-Host "      uploaded to R2." }
        else { Write-Warning "R2 attempt $try/5 failed; retrying in 60s"; if ($try -lt 5) { Start-Sleep 60 } }
    }
    if (-not $done) { Write-Warning "R2 upload failed - LOCAL dump is still safe; scheduler will retry." }
} else { Write-Host "[2/4] R2 upload skipped (disabled)" }

if ($PushToSupabase) {
    Write-Host "[3/4] Pushing into Supabase (overwrite; off-site DB + mobile). Retries if down."
    $done = $false
    for ($try = 1; $try -le 5 -and -not $done; $try++) {
        # --clean --if-exists: drop+recreate the app's objects so Supabase mirrors
        # local exactly. --no-owner/--no-acl: ignore local role ownership.
        & $PgRestore --clean --if-exists --no-owner --no-acl -d $SupabaseUrl $dump
        if ($LASTEXITCODE -eq 0) { $done = $true; Write-Host "      Supabase updated." }
        else { Write-Warning "Supabase push attempt $try/5 failed; retrying in 60s"; if ($try -lt 5) { Start-Sleep 60 } }
    }
    if (-not $done) { Write-Warning "Supabase push failed - LOCAL dump + R2 still safe; scheduler will retry." }
} else { Write-Host "[3/4] Supabase push skipped (disabled)" }

Write-Host "[4/4] Keeping the newest $KeepDumps dumps locally"
Get-ChildItem $BackupDir -Filter "asw-*.dump" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -Skip $KeepDumps |
  Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "Done. Latest backup: $dump"
