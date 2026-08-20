# Fix the cloud backup on the SERVER PC — step by step

Symptoms reported: **"cloud push not working"** and **"pg_dump is not installed."**

Root cause (almost always): the scheduled backup task runs as **SYSTEM**, which uses the
**machine PATH**. PostgreSQL *is* installed (your live "timber" DB runs on it), but its
`bin` folder is usually **not on PATH**, so the old script's bare `pg_dump` call failed —
looking like "pg_dump is not installed." AWS CLI (needed only for the R2 copy) may also be
missing.

**What's already fixed in the script:** `local-backup.ps1` now **auto‑finds** `pg_dump` /
`pg_restore` in `C:\Program Files\PostgreSQL\<ver>\bin` (no PATH change needed, works under
SYSTEM), has a **`-Check`** preflight, and **degrades gracefully** if AWS CLI is missing.

Do everything below **on the server PC**, in an **Administrator PowerShell**, in the folder
that holds `local-backup.ps1` (copy the latest `deploy/` folder onto the server PC first).

> 🔒 All passwords/keys go **only** into `local-backup.ps1` on this PC and the R2/Supabase
> dashboards. Never send them to anyone.

---

## Step 0 — Diagnose (30 seconds, touches nothing)

```powershell
cd C:\path\to\deploy          # wherever local-backup.ps1 lives on the server PC
powershell -ExecutionPolicy Bypass -File .\local-backup.ps1 -Check
```

It prints exactly what's found and what's missing, e.g.:

```
  pg_dump    : C:\Program Files\PostgreSQL\16\bin\pg_dump.exe
  aws        : not found (REQUIRED - R2 enabled)
   - R2 credentials ... still contain placeholders.
```

Fix each reported line using the steps below, then re‑run `-Check` until it says
**`preflight OK.`**

---

## Step 1 — Make sure `pg_dump` / `pg_restore` exist

The new script searches PATH **and** `C:\Program Files\PostgreSQL\*\bin`. So:

- If `-Check` shows a real path for `pg_dump` → **done, nothing to do.**
- If it shows **NOT FOUND**, confirm where PostgreSQL put them:
  ```powershell
  Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\pg_dump.exe" -ErrorAction SilentlyContinue
  ```
  - If that lists a file → the script will use it; re‑run `-Check`.
  - If it lists **nothing**, the client tools weren't installed with the server. Re‑run the
    **PostgreSQL installer** and tick **"Command Line Tools"** (this adds `pg_dump` /
    `pg_restore` / `psql`), or install just the tools, then re‑run `-Check`.

> Version note: the local `pg_dump` matches your local server (it dumps it), so step 1 is
> always fine. `pg_restore` into Supabase is forward‑compatible. If you ever upgrade local
> Postgres, keep the client tools on the same major version as the server.

---

## Step 2 — Install AWS CLI (only if you want the R2 off‑site copy)

R2 is the off‑site **file** copy. Two choices:

**Keep R2 (recommended):** install AWS CLI v2, then re‑run `-Check`.
```powershell
winget install -e --id Amazon.AWSCLI
# or download: https://awscli.amazonaws.com/AWSCLIV2.msi  (install "for all users")
```
Close and reopen the Admin PowerShell after installing so it's on PATH (the script also
looks in `C:\Program Files\Amazon\AWSCLIV2\aws.exe`).

**Skip R2 for now:** open `local-backup.ps1` and set
```powershell
$UploadToR2 = $false
```
Local dumps + Supabase still run. You can enable R2 later.

---

## Step 3 — Fill the CONFIG block in `local-backup.ps1`

Open `local-backup.ps1` in Notepad and replace the placeholders (values from the dashboards
you already control — do not paste them anywhere else):

| Setting | What to put |
|---|---|
| `$LocalPgPassword` | the **local** Postgres password for the `timber` role |
| `$BackupDir` | `D:\ASW-Backups` (or `C:\ASW-Backups` if there's no D: drive) |
| `$R2AccountId` | R2 dashboard → account id (skip if `$UploadToR2=$false`) |
| `$env:AWS_ACCESS_KEY_ID` / `$env:AWS_SECRET_ACCESS_KEY` | R2 API token (skip if R2 off) |
| `$SupabaseUrl` | Supabase → Project → Database → **Connection string → Session pooler (port 5432)**, put the DB password where it says `PASTE-DB-PASSWORD-HERE` |

Save. Re‑run **`-Check`** — it must print `preflight OK.`

> Use the Supabase **Session pooler (5432)** string, not the Transaction pooler (6543) —
> `pg_restore` needs a session connection.

---

## Step 4 — Run one real backup manually and verify

```powershell
powershell -ExecutionPolicy Bypass -File .\local-backup.ps1
```
Expected: `[1/4] … [2/4] … [3/4] … [4/4] … Done.` Then confirm all three copies:

1. **Local dump** — a new `asw-YYYY-MM-DD-HHMM.dump` in `D:\ASW-Backups`.
2. **R2** — the same file under `daily/` in the `abdul-sattar-woods-backups` bucket (R2 dashboard). *(skip if R2 off)*
3. **Supabase** — open the Supabase **Table editor**; the app's tables show today's data.

If any step warns, jump to **Troubleshooting** below — the local dump (step 1) still
succeeded, so your data is safe while you fix the push.

---

## Step 5 — (Re)register the scheduled task so it runs itself

Only needed if the task is missing or you want to reset it:
```powershell
powershell -ExecutionPolicy Bypass -File .\setup-backup-schedule.ps1
Start-ScheduledTask -TaskName "ASW Cloud Backup"     # fire one run now to test
```
Check it ran clean:
```powershell
Get-ScheduledTaskInfo -TaskName "ASW Cloud Backup"   # LastTaskResult should be 0
```
`LastTaskResult = 0` = success. It runs hourly 06:00–20:00, then 23:00/02:00/05:00, and
**catches up** the moment the PC/internet is back.

---

## Troubleshooting (by symptom)

- **`pg_dump not found`** → Step 1 (install "Command Line Tools", or it's not under
  `C:\Program Files\PostgreSQL\*\bin`).
- **`aws.exe not found`** → Step 2 (install AWS CLI, or set `$UploadToR2=$false`).
- **`...placeholder`** in `-Check` → Step 3 (a value in CONFIG wasn't filled).
- **Local dump fails, "password authentication failed"** → wrong `$LocalPgPassword`, or the
  `timber` role/DB doesn't exist (see `LOCAL_SETUP.md` Part A).
- **R2 attempt failed** → wrong R2 account id / keys, or no internet. Verify:
  ```powershell
  aws s3 ls "s3://abdul-sattar-woods-backups" --endpoint-url "https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com"
  ```
- **Supabase push failed, "SASL/password authentication"** → wrong DB password in
  `$SupabaseUrl`.
- **Supabase push failed, "SSL/connection"** → keep `?sslmode=require`; use the **Session
  pooler (5432)** string; check the Supabase project isn't paused (free projects pause when
  idle — open the dashboard once to wake it).
- **Scheduled task's `LastTaskResult` ≠ 0 but manual run works** → the task runs as SYSTEM;
  the new script no longer needs PATH for pg_dump, but AWS CLI must be installed **for all
  users** (default) so SYSTEM can see it. Re‑run the AWS installer "for all users" if needed.

---

## What "working" looks like when you're done
- `-Check` prints **`preflight OK.`**
- A manual run ends with **`Done.`** and you can see the dump in `D:\ASW-Backups`, in R2,
  and the data in Supabase.
- `Get-ScheduledTaskInfo -TaskName "ASW Cloud Backup"` shows **`LastTaskResult 0`**.
