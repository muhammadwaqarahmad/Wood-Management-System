# Local‑primary Setup — Abdul Sattar Woods (FAST)

**Decision:** the **main database is a local PostgreSQL on ONE office PC** (the "server"), reached by the other PCs over the office LAN — exactly like before, so the desktop app is **instant** (no cloud lag / no "Not Responding"). **Supabase becomes the backup** (off‑site copy + what the future mobile app reads). Cloudflare R2 keeps off‑site dump files.

```
   Server PC ── local PostgreSQL "timber"  ◀── the 5 office PCs connect over LAN (fast, <1ms)
        │
        └── twice-daily backup script (local-backup.ps1):
                 pg_dump local ─► dated .dump on disk
                                ├► Cloudflare R2         (off-site file copy)
                                └► push into Supabase    (off-site DB backup + mobile reads)
```

> The app **never ships data**. Master data is seeded **into the local PostgreSQL** once (Part B).

---

## Part A — Local PostgreSQL on the server PC (you)
1. Install **PostgreSQL** on the server PC if it isn't already (you had it before the cloud trial). Remember the `postgres` superuser password.
2. Create the app's role + database (pgAdmin, or `psql -U postgres`):
   ```sql
   CREATE ROLE timber LOGIN PASSWORD 'YOUR-LOCAL-PASSWORD';
   CREATE DATABASE timber OWNER timber;
   ```
3. Make it reachable on the LAN: in an **admin** PowerShell on the server PC, run
   `deploy/enable-lan-server.ps1` (sets `listen_addresses`, allows the office subnet in `pg_hba.conf`, opens firewall 5432, restarts PostgreSQL, and writes a ready **`CLIENT-LAN.env`** with this PC's IP).

## Part B — Seed the master data INTO the local database (ONCE)
Do this from the **server PC** (or any one client PC — your call):
1. Put **`deploy/MAIN-SERVER.env`** next to the exe as `.env` (server PC) — or `CLIENT-PC.env` if seeding from a client. Fill in the local Postgres password.
2. Add **one line** to that `.env`:  `TIMBER_SEED_MASTER_DATA=1`
3. **Launch the app once.** On first start it creates the schema and loads your **77 suppliers / 16 factories / 27 accounts** into the local PostgreSQL. Log in (`admin` / `admin123`), confirm the data is there.
4. **Remove that line again** (or set it to `0`) so it never re-seeds.
   *(This is the only time seeding runs — the data now lives in the shared local DB, and every PC reads it from there.)*

## Part C — Point all 5 PCs at the local database
1. **Server PC:** `MAIN-SERVER.env` → rename to `.env` next to the exe (host `127.0.0.1`).
2. **Other 4 PCs:** `CLIENT-PC.env` (or the `CLIENT-LAN.env` that Part A/3 generated with the correct IP) → rename to `.env` (host = the server PC's LAN IP).
3. Change the **admin password** from the default on first login.
4. Launch → **instant.** No lag, no freezing — the database is on the LAN.

## Part D — Supabase + R2 as the backup (you, one-time)
1. Install **AWS CLI** on the server PC (for R2) and confirm `pg_dump`/`pg_restore` work.
2. Fill the CONFIG block of **`deploy/local-backup.ps1`** (local Postgres password; R2 account/keys/bucket `abdul-sattar-woods-backups`; the Supabase push string — password only in the file).
3. Register the schedule: admin PowerShell → `deploy/setup-backup-schedule.ps1` (twice daily 13:00 + 17:30, with catch‑up + retry if the PC/internet was down).
4. Run once to confirm: a dated `.dump` in `D:\ASW-Backups`, the file in R2, and the data visible in the Supabase table editor.

## Part E — If the server PC dies (disaster recovery)
Restore the newest dump (local disk, else pulled from R2, else from Supabase) into PostgreSQL on any PC, run `enable-lan-server.ps1` on it, and point the other PCs' `.env` at its IP. Back to trading on the LAN. Worst‑case loss = since the last backup (a few hours).

---

## Why this is right for you
5 PCs in **one office on a LAN** → a local database answers in under a millisecond, so the desktop never waits. Supabase (Singapore) was ~150ms–2s per query, which froze the desktop screens. You keep Supabase's value (off‑site backup + mobile) without paying its latency on every click.

> 🔒 Passwords/keys live only in the `.env` files, `local-backup.ps1`, and the R2/Supabase dashboards — never sent to anyone.
