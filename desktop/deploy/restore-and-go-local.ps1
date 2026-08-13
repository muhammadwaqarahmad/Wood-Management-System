# ==========================================================================
#  DISASTER RECOVERY - "cloud is down": restore the newest backup into a
#  LOCAL PostgreSQL and point the app at it, so the business runs in LAN mode.
# --------------------------------------------------------------------------
#  Double-click (or run) this on the server PC. It:
#    1. finds the newest backup  (a local .dump, or pulls the latest from R2)
#    2. restores it into a local PostgreSQL database
#    3. rewrites the app's .env to LAN mode (localhost) on this PC
#  Then launch the app - it's running on local data, exactly like the old LAN.
#  When the cloud is back, restore the .env to the Supabase settings.
#
#  You lose at most the entries made SINCE the last nightly backup.
# ==========================================================================

# ---------- CONFIG --------------------------------------------------------
$BackupDir   = "D:\ASW-Backups"          # where local-backup.ps1 saves dumps
# The .env next to the exe on THIS pc (adjust <user> to this PC's Windows user):
$AppEnvPath  = "C:\Users\<user>\AppData\Local\Programs\Abdul Sattar Woods\.env"

# Local PostgreSQL to restore into + serve from. Same db/user your old LAN used,
# so the other PCs' CLIENT-PC.env (db=timber, user=timber) connects unchanged.
$LocalPgHost = "localhost"
$LocalPgPort = "5432"
$LocalPgUser = "timber"
$LocalPgDb   = "timber"
$LocalPgPassword = "PASTE-LOCAL-POSTGRES-PASSWORD-HERE"   # same one your old LAN .env used

# OPTIONAL - pull the newest dump from Cloudflare R2 if no local one is found:
$UseR2        = $true
$R2AccountId  = "<R2_ACCOUNT_ID>"
$R2Bucket     = "abdul-sattar-woods-backups"
$env:AWS_ACCESS_KEY_ID     = "<R2_ACCESS_KEY_ID>"
$env:AWS_SECRET_ACCESS_KEY = "<R2_SECRET_KEY>"
$env:AWS_DEFAULT_REGION    = "auto"
# --------------------------------------------------------------------------

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

# 1) find newest local dump; else fetch newest from R2
$dump = Get-ChildItem $BackupDir -Filter "asw-*.dump" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $dump -and $UseR2) {
    Write-Host "No local dump; fetching newest from R2..."
    $ep = "https://$R2AccountId.r2.cloudflarestorage.com"
    $key = (& aws s3 ls "s3://$R2Bucket/daily/" --endpoint-url $ep | Sort-Object | Select-Object -Last 1).Split()[-1]
    $dest = Join-Path $BackupDir $key
    & aws s3 cp "s3://$R2Bucket/daily/$key" $dest --endpoint-url $ep
    $dump = Get-Item $dest
}
if (-not $dump) { throw "No backup found locally or in R2." }
Write-Host "Using backup: $($dump.FullName)"

# 2) restore into local Postgres
$env:PGPASSWORD = $LocalPgPassword
& psql -h $LocalPgHost -p $LocalPgPort -U $LocalPgUser -d postgres -v ON_ERROR_STOP=1 `
      -c "DROP DATABASE IF EXISTS $LocalPgDb;" -c "CREATE DATABASE $LocalPgDb;"
& pg_restore -h $LocalPgHost -p $LocalPgPort -U $LocalPgUser -d $LocalPgDb --no-owner $dump.FullName
Write-Host "Restored into local db '$LocalPgDb'."

# 3) point the app at local Postgres (LAN mode)
$envText = @"
TIMBER_DB_BACKEND=postgresql
TIMBER_PG_HOST=$LocalPgHost
TIMBER_PG_PORT=$LocalPgPort
TIMBER_PG_USER=$LocalPgUser
TIMBER_PG_PASSWORD=$LocalPgPassword
TIMBER_PG_DB=$LocalPgDb
TIMBER_PG_SSLMODE=
TIMBER_PG_CONNECT_TIMEOUT=8
TIMBER_PG_STATEMENT_TIMEOUT=30000
TIMBER_AUDIT_RETENTION_DAYS=3
TIMBER_SEED_MASTER_DATA=0
TIMBER_LANG=ur
"@
Copy-Item $AppEnvPath "$AppEnvPath.cloud.bak" -Force -ErrorAction SilentlyContinue
Set-Content -Path $AppEnvPath -Value $envText -Encoding utf8
Write-Host "App .env switched to LOCAL mode (backup of cloud .env saved as .env.cloud.bak)."
Write-Host "Launch the app now - it runs on local data. Point other PCs' .env at this PC's IP for LAN."
