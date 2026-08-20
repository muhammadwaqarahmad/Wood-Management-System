# ==========================================================================
#  ONE-COMMAND PORTABLE EXPORT of the cloud database (Railway or any Postgres).
#  Produces a dated .dump you can restore into ANY Postgres later (DigitalOcean,
#  a new Railway project, your local PC) — so you are never locked to one host.
#
#  Usage (from this folder):
#    # option 1 - pass the URL:
#    .\cloud-pg-export.ps1 -Url "postgresql://user:pass@host:port/db"
#    # option 2 - set it once, then just run the script:
#    $env:DATABASE_URL = "postgresql://user:pass@host:port/db"
#    .\cloud-pg-export.ps1
#
#  Where to get the URL: Railway -> Postgres service -> "Connect" ->
#  "Public Network" -> copy the connection string (needs the PUBLIC one to reach
#  it from your PC; the internal one only works inside Railway).
#
#  Restore the file into any Postgres later:
#    pg_restore --clean --if-exists --no-owner --no-acl -d "<TARGET_DB_URL>" "<the .dump>"
#
#  Needs pg_dump (ships with PostgreSQL). This script auto-finds it even if it is
#  not on PATH (same as local-backup.ps1).
# ==========================================================================

param(
    [string]$Url = $env:DATABASE_URL,
    [string]$OutDir = ".\cloud-exports"
)

$ErrorActionPreference = "Stop"

if (-not $Url) {
    throw "No connection URL. Pass -Url '<postgresql://...>' or set `$env:DATABASE_URL. " +
          "Get it from Railway -> Postgres -> Connect -> Public Network."
}

# --- locate pg_dump (PATH, else the standard PostgreSQL install folder) ---
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
$pgDirs = @("C:\Program Files\PostgreSQL\*\bin", "C:\Program Files (x86)\PostgreSQL\*\bin")
$PgDump = Find-Tool "pg_dump.exe" ($pgDirs | ForEach-Object { Join-Path $_ "pg_dump.exe" })
if (-not $PgDump) {
    throw "pg_dump not found. Install the PostgreSQL client tools (they ship with PostgreSQL)."
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
$out = Join-Path $OutDir "asw-cloud-$stamp.dump"

Write-Host "Exporting cloud database -> $out"
Write-Host "  (using $PgDump)"
# -Fc = compressed custom format (restores with pg_restore); --no-owner/--no-acl
# so it restores cleanly onto ANY host regardless of local roles.
& $PgDump -Fc --no-owner --no-acl -d $Url -f $out
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed ($LASTEXITCODE)" }

$mb = [math]::Round((Get-Item $out).Length / 1MB, 2)
Write-Host ""
Write-Host "DONE. Portable copy: $out  ($mb MB)"
Write-Host ""
Write-Host "Restore into ANY Postgres later with:"
Write-Host "  pg_restore --clean --if-exists --no-owner --no-acl -d `"<TARGET_DB_URL>`" `"$out`""
