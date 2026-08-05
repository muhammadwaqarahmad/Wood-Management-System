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
#    - PostgreSQL  (pg_dump / pg_restore / psql)   - installed for the local DB
#    - AWS CLI     (R2 is S3-compatible)           - or set $UploadToR2 = $false
# ==========================================================================

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
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$dump  = Join-Path $BackupDir "asw-$stamp.dump"
$env:PGPASSWORD = $LocalPgPassword

Write-Host "[1/4] Dumping LOCAL db '$LocalPgDb' -> $dump"
& pg_dump -h $LocalPgHost -p $LocalPgPort -U $LocalPgUser -d $LocalPgDb -Fc -f $dump
if ($LASTEXITCODE -ne 0) { throw "local pg_dump failed ($LASTEXITCODE)" }
Write-Host "      size: $([math]::Round((Get-Item $dump).Length/1MB,2)) MB  (this is the guaranteed backup)"

if ($UploadToR2) {
    Write-Host "[2/4] Uploading to Cloudflare R2 (retries if internet is down)"
    $done = $false
    for ($try = 1; $try -le 5 -and -not $done; $try++) {
        & aws s3 cp $dump "s3://$R2Bucket/daily/asw-$stamp.dump" `
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
        & pg_restore --clean --if-exists --no-owner --no-acl -d $SupabaseUrl $dump
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
