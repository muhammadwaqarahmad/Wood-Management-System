# Wood Management System — Abdul Sattar Woods · عبدالستار ووڈز

A complete accounting & business-management platform for a **timber commission
business** — it buys timber from suppliers (*baparis*) and sells to factories,
and tracks every trade, payment, ledger, and rupee of profit in between.

Built as **one system with three faces**: a fast Windows **desktop app** for
daily data entry, a **mobile app** (Android + iPhone) for viewing on the go, and
an always-on **cloud API** so the phones work anywhere — all sharing the same
accounting engine. Fully **bilingual (English / اردو)** with right-to-left support.

> Profit per load = (factory rate − supplier rate) × weight

> ⚠️ **Proprietary software.** This is a closed commercial product, **not
> open-source**. Any use requires a paid license / purchased key — see
> [LICENSE](LICENSE).

---

## What it does

- **Trades** — record purchases from suppliers and sales to factories (weight,
  rate, freight, vehicle, wood type).
- **Payments** — money paid to suppliers / received from factories, in both
  directions (cash, bank, online, cheque), auto-allocated to loads (FIFO).
- **Ledgers** — per-party running statements, factory sub-ledgers (weekly /
  irregular split), trade ledger, profit ledger, financial position.
- **Money** — bank accounts, bank book, transfers, expenses, cheques, loans.
- **Reports & Dashboard** — sales / purchases / profit, cash-flow, per-party
  performance, overdue & aging buckets, daily book (روزنامچہ).
- **Master data** — suppliers, factories, wood types.
- **Security** — user accounts with roles, audit log, JWT-secured API, and
  fingerprint / Face-ID unlock on mobile.
- **Bilingual & themeable** — every screen switches between English and Urdu
  (RTL), plus light / dark themes.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| **Desktop app** | Python 3.12, **PyQt6** (Qt Widgets), SQLAlchemy 2.0 ORM, Alembic migrations |
| **Database** | **PostgreSQL** (LAN / production), SQLite (standalone), **Supabase** (cloud) |
| **Backend / API** | **FastAPI**, Uvicorn, PyJWT (access + rotating refresh tokens), bcrypt |
| **Mobile app** | **Flutter / Dart**, Riverpod (state), dio (HTTP), flutter_secure_storage, local_auth (biometrics) |
| **Cloud / infra** | Supabase (Postgres), Render (API hosting), Cloudflare R2 (off-site backups), Docker |
| **Reports** | ReportLab (PDF), openpyxl (Excel), Urdu shaping (arabic-reshaper + python-bidi) |

Switching SQLite ↔ PostgreSQL is one setting in
[`timber/config.py`](timber/config.py) (`DB_BACKEND`) or the
`TIMBER_DB_BACKEND` environment variable.

---

## Architecture

```
  Windows desktop app ──writes──►  LOCAL PostgreSQL   (fast, primary on the office LAN)
        │
        └── twice-daily backup ──►  SUPABASE Postgres (cloud) ──►  Cloudflare R2 (off-site)
                                          ▲
                                          │ reads (read-only)
                           Cloud API (FastAPI on Render, always-on)
                                          ▲
                                          │ HTTPS, from anywhere
                                   📱 Mobile app (Android / iPhone)
```

- The **desktop** app uses the **local** database for speed (all data entry).
- The **mobile** app is **read-only** and reads the **cloud** copy, so it works
  24/7 — even when the office PC is off. Write actions on mobile are shown but
  intentionally disabled (data is entered on the desktop).

---

## Repository layout

```
timber/            Core Python package (shared by desktop + API)
  core/            Business logic: ledgers, payments, reports, dashboard, auth
  db/              SQLAlchemy models, engine, Alembic migrations
  ui/              PyQt desktop screens
  api/             FastAPI app + routers (read-only mobile API)
mobile/            Flutter mobile app (lib/, android/, ...)
deploy/            Cloud + LAN setup, backups, and the cloud-API Docker package
  cloud-api/       Dockerfile, render.yaml, requirements for the always-on API
requirements.txt   Desktop Python dependencies
```

---

## Running it

### Desktop app (Windows)
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m alembic upgrade head     # create / update the schema
python run.py                      # launch the desktop app
```
Configure the database via environment variables or a `.env` next to the exe —
see [`deploy/LOCAL_SETUP.md`](deploy/LOCAL_SETUP.md).

### API (local test)
```powershell
pip install -r deploy/cloud-api/requirements-api.txt
uvicorn timber.api.main:app --host 0.0.0.0 --port 8000
# health check: http://localhost:8000/health
```

### Cloud API (always-on, for mobile)
Deploy the container in [`deploy/cloud-api/`](deploy/cloud-api/) to Render (or
any Docker host), pointed at Supabase. Full guide:
[`deploy/MOBILE_CLOUD_API.md`](deploy/MOBILE_CLOUD_API.md).

### Mobile app (Flutter)
```powershell
cd mobile
flutter pub get
flutter build apk --release --dart-define=API_URL=https://<your-api-url>
```
Install the resulting `.apk` on Android. iOS builds require macOS (or a cloud-Mac
service such as Codemagic — a `codemagic.yaml` is included). Inside the app you
can also set the server address on the login screen (no rebuild needed).

---

## First login

The app creates a default administrator account on first setup:

- **Username:** `admin`
- **Initial password:** `admin123`

> 🔒 **Change this password immediately after the first login.** Never expose the
> app or its API to the internet while the default password is still active.
> Additional users and roles are managed inside the app.

---

## Security & data

- Passwords are hashed with **bcrypt**; the API issues **JWT** access + rotating
  refresh tokens. The mobile app stores the refresh token in the device's secure
  keystore (Keychain / Keystore) and never saves the password.
- Real credentials (database passwords, API secrets, cloud keys) live only in
  local `.env` files and host dashboards — they are **git-ignored** and never
  committed to this repository.

---

## License

© 2026 Muhammad Waqar Ahmad. All rights reserved.
**Proprietary / commercial** — use requires a paid license or purchased key.
See [LICENSE](LICENSE). For licensing, contact the owner via
[github.com/muhammadwaqarahmad](https://github.com/muhammadwaqarahmad).
