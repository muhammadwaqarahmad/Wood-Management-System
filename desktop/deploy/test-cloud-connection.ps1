# ==========================================================================
#  STEP-1 CHECK - is the cloud reachable, and how FAST is it from this PC?
#
#  Run on any PC after you've filled in its .env:
#      powershell -ExecutionPolicy Bypass -File .\test-cloud-connection.ps1
#      powershell -ExecutionPolicy Bypass -File .\test-cloud-connection.ps1 -EnvPath "C:\path\to\.env"
#
#  It connects with the .env's Supabase settings and times 10 round-trips, so
#  you know the real latency (Karachi -> Singapore) before rolling out. Needs
#  psql on PATH (comes with PostgreSQL). Nothing is written to the database.
# ==========================================================================

param(
    # Default: the .env next to the installed exe. Point -EnvPath at your file.
    [string]$EnvPath = "$env:LOCALAPPDATA\Programs\Abdul Sattar Woods\.env"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path $EnvPath)) { throw ".env not found at $EnvPath - pass -EnvPath 'C:\...\.env'" }

# Parse the TIMBER_PG_* keys from the .env.
$cfg = @{}
foreach ($line in Get-Content $EnvPath) {
    if ($line -match "^\s*([A-Z_]+)\s*=\s*(.*)$") { $cfg[$Matches[1]] = $Matches[2].Trim() }
}
foreach ($k in "TIMBER_PG_HOST","TIMBER_PG_USER","TIMBER_PG_PASSWORD","TIMBER_PG_DB") {
    if (-not $cfg[$k]) { throw "$k missing from $EnvPath" }
}

$pgHost = $cfg["TIMBER_PG_HOST"]
$port   = if ($cfg["TIMBER_PG_PORT"]) { $cfg["TIMBER_PG_PORT"] } else { "5432" }
$db     = $cfg["TIMBER_PG_DB"]
$user   = $cfg["TIMBER_PG_USER"]
$env:PGPASSWORD = $cfg["TIMBER_PG_PASSWORD"]
$env:PGSSLMODE  = if ($cfg["TIMBER_PG_SSLMODE"]) { $cfg["TIMBER_PG_SSLMODE"] } else { "require" }
$env:PGCONNECT_TIMEOUT = "8"

Write-Host "Connecting to ${pgHost}:$port  db=$db  user=$user  ssl=$env:PGSSLMODE"
$probe = & psql -h $pgHost -p $port -U $user -d $db -tAc "select 1;" 2>&1
if ($LASTEXITCODE -ne 0 -or "$probe".Trim() -ne "1") {
    Write-Host ""
    Write-Host "FAILED to connect:" -ForegroundColor Red
    Write-Host $probe
    Write-Host "Check: password correct? pooler host + session port 5432? sslmode=require? internet up?"
    exit 1
}
Write-Host "Connected OK." -ForegroundColor Green

# Time 10 round-trips to measure real latency.
$times = @()
for ($i = 1; $i -le 10; $i++) {
    $ms = (Measure-Command { & psql -h $pgHost -p $port -U $user -d $db -tAc "select 1;" | Out-Null }).TotalMilliseconds
    $times += $ms
}
$avg = [math]::Round(($times | Measure-Object -Average).Average, 0)
$min = [math]::Round(($times | Measure-Object -Minimum).Minimum, 0)
$max = [math]::Round(($times | Measure-Object -Maximum).Maximum, 0)

Write-Host ""
Write-Host "Round-trip latency over 10 queries:  avg ${avg}ms   (min ${min}ms, max ${max}ms)"
if     ($avg -lt 400)  { Write-Host "=> Excellent for a shared cloud DB. Roll out to the other PCs." -ForegroundColor Green }
elseif ($avg -lt 800)  { Write-Host "=> Fine for daily use (pages are batched to one round-trip each)." -ForegroundColor Green }
else                   { Write-Host "=> High - check Wi-Fi/ISP, or reconsider the region." -ForegroundColor Yellow }
Write-Host "(Note: this measures psql's per-call connect+query; the app keeps a"
Write-Host " pooled connection open, so in-app queries are faster than this.)"
