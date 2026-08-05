# Mobile Cloud API — see data any time, any place

Goal: the phone app works **24/7 from anywhere** (mobile data or any WiFi),
even when the office PC is **off** — by reading from **Supabase** (your
always-on cloud database) through a small **always-on API in the cloud**.

```
  Office PC (desktop app) ──writes──► LOCAL Postgres  (fast, primary)
        │
        └── local-backup.ps1 (twice daily) ──► SUPABASE Postgres (cloud, always on)
                                                     ▲
                                                     │ reads (read-only)
                              Cloud API (Render) ────┘
                                     ▲
                                     │ https, from anywhere
                              📱 Mobile app
```

The desktop app is **unchanged** — it keeps using the fast local server. Only
the phone reads from the cloud copy.

> **Data freshness:** the phone shows data **as of the last backup** to Supabase
> (the 13:00 and 17:30 syncs). So at night you see the full day's data as long as
> the evening backup ran. It is not second-by-second live — that's the trade-off
> for working while the office PC is off. (If you ever want live, the desktop
> would have to write straight to the cloud, which we deliberately avoided
> because cloud latency froze the desktop UI.)

---

## What you deploy (once)

The cloud API is the **same code** as the office API, containerised
(`deploy/cloud-api/Dockerfile`) and pointed at Supabase via env vars. It is
**read-only** (the mobile app has no write endpoints), so there is no risk of
it changing your data.

### Option 1 — Render.com (recommended, has a free tier)

1. Push this repo to **GitHub** (private is fine).
2. Render → **New + → Blueprint** → connect the repo → it reads
   `deploy/cloud-api/render.yaml` and creates the **asw-api** service.
3. In the service's **Environment**, set the two secrets:
   - `TIMBER_PG_PASSWORD` = your Supabase database password
   - `TIMBER_API_SECRET` = a long random string (e.g. 40+ chars)
4. Deploy. When it's live you get a URL like `https://asw-api.onrender.com`.
5. Open `https://asw-api.onrender.com/health` in a browser → you should see
   `{"ok":true,...,"backend":"postgresql"}`. That confirms it reached Supabase.

> Render **free** sleeps after ~15 min idle, so the *first* open after a quiet
> spell takes ~50s to wake, then it's fast. To keep it instant, upgrade that
> service to **Starter ($7/mo)**, or ping `/health` every 10 min with
> cron-job.org (same trick as the DB keep-alive).

### Option 2 — any Docker host (Railway, Fly.io, Cloud Run, a VPS)

Build + run the same image; set the env vars from
`deploy/cloud-api/cloud-api.env.example`:
```
docker build -f deploy/cloud-api/Dockerfile -t asw-api .
docker run -p 8000:8000 --env-file deploy/cloud-api/cloud-api.env asw-api
```

---

## Point the phone at the cloud (no rebuild needed)

The app already has an in-app **Server** field (login screen → "Server", or
Settings → Connection → Server). Just enter the cloud URL once:

```
https://asw-api.onrender.com
```

That's it — the phone now works from anywhere, office PC on or off. You can
switch back to the office LAN address any time from the same field.

(If you'd rather bake the cloud URL in as the default so nothing needs typing,
rebuild the APK with `--dart-define=API_URL=https://asw-api.onrender.com`.)

---

## Login on the cloud

Login uses the **users table in Supabase** (synced from local). The same
usernames/passwords work. If you haven't yet, change the default `admin`
password on the desktop app — it flows to the cloud on the next backup.

---

## Bake the cloud URL into the app (no typing on each phone)

Once you have the Render URL, build an APK with it as the built-in default:

```powershell
powershell -File deploy\cloud-api\build-cloud-apk.ps1 -Url https://asw-api.onrender.com
```

That produces `AbdulSattarWoods.apk` (root folder) pre-pointed at the cloud —
install it on every phone and they just log in, nothing to configure. (The
in-app **Server** field still works if you ever need to switch.)

Or send me the Render URL and I'll build it for you.

---

## Keep the cloud API awake (so there's no cold-start wait)

Render's **free** service sleeps after ~15 min idle. Ping `/health` every few
minutes to keep it warm. `/health` is public (no secret), so pick either:

**A. cron-job.org (recommended — most reliable, free):**
1. Sign up at cron-job.org.
2. New cronjob → URL `https://<your-service>.onrender.com/health`, method GET.
3. Schedule: every **10 minutes**. Save. Done.

**B. GitHub Action (already in this repo — no extra account):**
- File `.github/workflows/keepalive.yml` pings every 10 min.
- Activate it: GitHub → repo → Settings → *Secrets and variables → Actions →
  Variables* → add `API_HEALTH_URL = https://<your-service>.onrender.com/health`.
- (GitHub disables schedules after 60 days of no repo commits, and timing can
  drift a few minutes — cron-job.org is steadier, so prefer A for keep-warm.)

> Or skip keep-alive entirely and upgrade the Render service to **Starter
> ($7/mo)** — it never sleeps and is a bit faster.

---

🔒 **Never paste the Supabase password or API secret to me.** They go only into
the host's dashboard (Render Environment) and your `.env` files.
