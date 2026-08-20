# Deploy the website on Railway (frontend + API + Postgres, one project)

All three run in **one Railway project, same region (Singapore)** — so the API talks
to the database over Railway's private network (~1–5ms/query = fast), and you have one
dashboard and one bill. You are never locked in: `cloud-pg-export.ps1` gives you a
portable copy you can restore onto DigitalOcean (or anywhere) later.

## What I already set up (in the repo)
- `website/railway.json` — builds & runs the Next.js **web** service.
- `desktop/railway.json` — builds the FastAPI **api** service from your Dockerfile.
- `desktop/deploy/cloud-pg-export.ps1` — one‑command portable database export.

The API **self‑migrates** on first boot (creates all tables in the Railway Postgres),
so there's no manual DB setup.

---

## What YOU do (once, ~20 minutes)

### 0. Put the code on GitHub
Railway deploys from GitHub. Push this repo to a GitHub repo (private is fine).
*(This is the moment your "don't push yet" hold ends — tell me and I can commit + push, or do it yourself.)*

### 1. Create the project + database
1. railway.app → **New Project → Deploy from GitHub repo** → pick the repo.
2. **New → Database → PostgreSQL.** Rename the service to **`Postgres`**.
3. Open each service's **Settings → Region → Singapore (Southeast Asia)** so all three sit together.

### 2. Add the **api** service
1. **New → GitHub Repo** (same repo) → name it **`api`**.
2. Settings → **Root Directory = `desktop`** (it reads `desktop/railway.json` → your Dockerfile).
3. Settings → **Variables**, add these (the `${{Postgres.*}}` ones auto‑link to the DB):

   | Variable | Value |
   |---|---|
   | `TIMBER_DB_BACKEND` | `postgresql` |
   | `TIMBER_PG_HOST` | `${{Postgres.PGHOST}}` |
   | `TIMBER_PG_PORT` | `${{Postgres.PGPORT}}` |
   | `TIMBER_PG_USER` | `${{Postgres.PGUSER}}` |
   | `TIMBER_PG_PASSWORD` | `${{Postgres.PGPASSWORD}}` |
   | `TIMBER_PG_DB` | `${{Postgres.PGDATABASE}}` |
   | `TIMBER_API_SECRET` | a long random string (JWT key) — 🔒 your secret |
   | `TIMBER_API_CORS` | `*` (tighten in step 5) |

   *(Leave `TIMBER_PG_SSLMODE` unset — the private network doesn't need it.)*
4. Deploy. When it's green, **Settings → Networking → Generate Domain**. Copy the URL
   (e.g. `https://api-production-xxxx.up.railway.app`) and open `.../health` — it should say `{"ok":true}`.

### 3. Add the **web** service
1. **New → GitHub Repo** (same repo) → name it **`web`**.
2. Settings → **Root Directory = `website`** (reads `website/railway.json`).
3. Settings → **Variables**, add:

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://${{api.RAILWAY_PUBLIC_DOMAIN}}` |

   *(This is baked in at build time, so it must be set before the web build — it is, since you add it now.)*
4. Deploy → **Generate Domain** for `web`. That URL is your website.

### 4. First login
Open the `web` URL → sign in **admin / admin123** → **change the admin password immediately.**
(The DB was created empty + migrated; you can add data, or load the office data in step 6.)

### 5. Lock down CORS (after it works)
On the **api** service, change `TIMBER_API_CORS` from `*` to your web URL:
`https://${{web.RAILWAY_PUBLIC_DOMAIN}}` → redeploy the api. Now only your site can call the API.

### 6. (Optional) Load the existing office data
The cloud DB starts empty. To put your real data in it, restore a dump of the office
database into the Railway Postgres (get the Railway **public** DB URL from
Postgres → Connect → Public Network):
```powershell
pg_restore --clean --if-exists --no-owner --no-acl -d "<RAILWAY_PUBLIC_DB_URL>" "D:\ASW-Backups\asw-<latest>.dump"
```

### 7. (Optional) Custom domain
Each service → Settings → Networking → **Custom Domain** (e.g. `app.abdulsattarwoods.com`)
and add the CNAME it shows at your domain registrar. Update `NEXT_PUBLIC_API_URL` /
`TIMBER_API_CORS` to the custom domains and redeploy.

---

## Your "never locked in" export (run anytime)
```powershell
cd desktop\deploy
$env:DATABASE_URL = "<Railway Postgres PUBLIC connection string>"
.\cloud-pg-export.ps1
```
→ writes `cloud-exports\asw-cloud-<date>.dump`. To move to DigitalOcean later: create a
Postgres there, `pg_restore` that file into it, repoint `TIMBER_PG_*`, done — all data intact.

## Costs & notes
- Railway is usage‑based (~$5/mo base + usage; a small app is typically ~$10–20/mo).
- Keep all three services in **Singapore** (never split API and DB across regions).
- 🔒 Secrets (`TIMBER_API_SECRET`, DB password) live only in the Railway dashboard — never in git.
