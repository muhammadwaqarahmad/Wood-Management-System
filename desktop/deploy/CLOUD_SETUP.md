# Supabase Cloud Setup — Abdul Sattar Woods

Live database on **Supabase (free, Singapore)** — this is the **main storage** every PC (and later, the phones) connects to. Two backups are **copies pulled FROM Supabase**, twice a day — **no GitHub needed**:
- **Local mirror** — restored into your existing local PostgreSQL as the **`timber`** database on **one backup PC you choose**, so you can open it in pgAdmin and see the live data any time. **This is also your full fallback:** if Supabase ever goes down for good — or you hit the free limit and want out — one script (`enable-lan-server.ps1`) turns this PC into the **main LAN server** and the other 4 PCs connect to it exactly like the old LAN setup. No data stuck in the cloud. (See Part F.)
- **Off-site** — the *same* script uploads the dump to **Cloudflare R2** (bucket `abdul-sattar-woods-backups`; R2 auto-deletes copies older than 90 days).

Anti-pause: the backup's `pg_dump` touches Supabase twice every working day, so it never pauses in normal use. **Missed backups catch up automatically:** if the PC was off (or the internet was down) at 13:00/17:30, the scheduled task fires the moment the PC + internet are back — you never silently skip a window (set up via `setup-backup-schedule.ps1`, Part D). A **cron-job.org** ping every 3 days is the extra safety net for a long closure (5+ days) when the backup PC is off entirely.

Your Supabase project: **ref `piqrfdwirbpbfcdibdmh`**, region **Singapore (ap-southeast-1)**.

Usage: ~5 PCs (desktop app) + 3–4 phones (mobile app, later).

---

## Architecture
```
   Supabase Postgres (Singapore, free) ──── live DB, all PCs + phones connect
        │  (pooler, session mode, SSL)
        │
        └── twice-daily backup PC script (local-backup.ps1):
                 pg_dump ─► local PostgreSQL "timber" db (browse it in pgAdmin)
                         └► Cloudflare R2  (off-site, lifecycle auto-delete >90d)

   cron-job.org ──(every 3 days)──► rpc/keepalive  (only matters during a
                                    5+ day closure; prevents the 7-day pause)
```

---

## STEP 0 — starting FRESH (decided)

Your local `timber` is just test data, so we start the cloud empty and seed your master data. **Nothing to migrate.** Just do the seeding in **Part B/3** below. (If that ever changes and you need to move an existing database up, ask me — it's a two-command `pg_dump` → `pg_restore`.)

---

## Part A — Create the Supabase project (you)
1. Already created (ref `piqrfdwirbpbfcdibdmh`, Singapore). Keep the **database password** safe.
2. Project Settings → Database → **Connection Pooling** → **Session** mode → the string is:
   `postgresql://postgres.piqrfdwirbpbfcdibdmh:<PASSWORD>@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`
   *(This is the POOLER host — gives the IPv4 the office PCs need. Session mode = port 5432.)*

## Part B — Point the app at Supabase (mostly done for you)
1. **`deploy/ASW-CLOUD.env`** is ready — the SAME file for all 5 PCs. On one PC first: copy it into the exe folder `C:\Users\<user>\AppData\Local\Programs\Abdul Sattar Woods\`, **rename to `.env`**, and paste your DB password on the `TIMBER_PG_PASSWORD` line. (Nothing else to edit — host/user/region/SSL are already correct.)
2. **Verify + measure speed (before rolling out):** run `deploy/test-cloud-connection.ps1` → it confirms the connection and prints the real Karachi→Singapore latency, so you know it's fast enough before touching the other PCs.
3. **Seed your master data (fresh start):** in that `.env`, temporarily set `TIMBER_SEED_MASTER_DATA=1`, launch the app once (it creates the schema and loads the 77 suppliers / 16 factories / 27 accounts), log in, close it, then set it **back to `0`**. *(Alternative on a dev machine with Python: `python -m timber.db.seed_master`. Idempotent; review the transliterated Urdu names after.)*
4. Launch → check login, an entry, ledgers, dashboard, speed → then copy the finished `.env` (password filled, seed `=0`) to the other 4 PCs.

## Part C — Cloudflare R2 (you, one-time)
1. Create the R2 **bucket** named exactly **`abdul-sattar-woods-backups`** (all lowercase — R2 requires it).
2. Create an **API token** → note the **Account ID**, **Access Key ID**, **Secret**.
3. Add a **Lifecycle rule** on the bucket: delete objects older than 90 days.
4. You'll paste the Account ID / keys into the **CONFIG block of `local-backup.ps1`** on the backup PC — *not* to me.

## Part D — Twice-daily backup on the backup PC (you)
1. Install **AWS CLI** (R2 is S3-compatible; install for "all users"). Confirm **PostgreSQL** is installed (for the local `timber` mirror).
2. Put `deploy/local-backup.ps1` **and** `deploy/setup-backup-schedule.ps1` on the backup PC (same folder). Fill the CONFIG block of `local-backup.ps1`: paste the Supabase DB password into `$SupabaseUrl`, your local Postgres password into `$LocalPgPassword`, and the R2 Account ID + keys. (Bucket + Supabase host/user are already filled in.)
3. In an **admin** PowerShell, run `setup-backup-schedule.ps1` **once**. It registers both runs (**13:00** + **17:30**) with **catch-up** (runs when the PC returns) and **retry-on-failure** (runs when the internet returns) — so a missed window is never lost. No manual Task Scheduler clicking.
4. Test now: `Start-ScheduledTask -TaskName "ASW Cloud Backup"` → confirm a dated `.dump` appears in `D:\ASW-Backups`, the local `timber` db is rebuilt (open it in pgAdmin), and the file appears in R2.

## Part E — Keep-alive for long closures (you, one-time)
1. Supabase → SQL Editor → run **`deploy/keepalive.sql`**.
2. **cron-job.org** (free) → new job → POST `https://piqrfdwirbpbfcdibdmh.supabase.co/rest/v1/rpc/keepalive`, headers `apikey` and `Authorization: Bearer` = your **anon** key, body `{}`, **schedule every 3 days**.

## Part F — Fallback: run on the LAN if the cloud dies / you leave the free tier
Two scripts, run on the backup PC (the one with the local `timber` mirror):
1. **`deploy/restore-and-go-local.ps1`** — restores the newest dump into local `timber` and flips **this PC's** `.env` to LAN mode. Launch the app → it's already trading on local data.
2. **`deploy/enable-lan-server.ps1`** (admin, once) — makes this PC's PostgreSQL accept LAN connections (listen address, `pg_hba`, firewall port 5432, service restart) and writes a ready **`CLIENT-LAN.env`** with this PC's IP already filled in.
3. On the other 4 PCs: copy `CLIENT-LAN.env` to the exe folder as `.env`, paste the local Postgres password, launch → all 5 back on the LAN, exactly like before.

When Supabase is back (and if you want the cloud again), put `ASW-CLOUD.env` back as `.env` on each PC. Worst-case loss = since the last backup (a few hours). This is your guarantee that **your data is never trapped in the cloud.**

---

## Status of what I needed from you
1. **Supabase created / Singapore / string** — ✅ done (ref `piqrfdwirbpbfcdibdmh`).
2. **Master data** — ✅ start FRESH + seed the 77/16/27 (Part B/3). No migration.
3. **R2 bucket** — ✅ `abdul-sattar-woods-backups` (lowercased for you).
4. **Backup target** — ✅ local Postgres `timber` db on your chosen backup PC (dumps in `D:\ASW-Backups`; change the drive if there's no `D:`).
5. **Frequency** — ✅ twice daily (13:00 + 17:30).

> 🔒 **Never paste real passwords / API secrets to me.** They belong only in the `.env` (next to the exe), `local-backup.ps1` on the backup PC, and the R2 / cron-job.org dashboards.
