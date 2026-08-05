# Abdul Sattar Woods — عبدالستار ووڈز

Desktop app for managing wood trading between **baparis** (suppliers) and
**factories** (buyers): ledgers, payments, profit tracking, and reports.
Fully bilingual — **English or Urdu** (single-language UI), switchable at
login or in Settings; Urdu uses right-to-left layout. Language is stored
per-PC in `storage/settings.json` ([i18n.py](timber/i18n.py)).

> Profit per load = (factory rate − bapari rate) × weight

## Tech stack

Python 3.11+ · PyQt6 · SQLAlchemy · SQLite (dev) / PostgreSQL (LAN prod) ·
ReportLab + openpyxl (reports) · bcrypt (auth) · PyInstaller (.exe).

Switching SQLite ↔ PostgreSQL is one line in [timber/config.py](timber/config.py)
(`DB_BACKEND`) or the `TIMBER_DB_BACKEND` env var.

## Project layout (4-layer architecture)

```
timber/
  app.py            entry point (QApplication bootstrap)
  config.py         settings + DB backend switch
  ui/               presentation layer  (windows, screens, widgets)
  core/             business logic       (auth, calculations, ledgers)
  db/               data-access layer
    engine.py       SQLAlchemy engine + session + Base
    models/         ORM models           (Phase 1)
    repositories/   query/persistence    (Phase 1+)
  utils/            shared helpers
  resources/        fonts, icons, styles
storage/            runtime data: sqlite db, backups, reports, logs (git-ignored)
run.py              convenience launcher
```

## Setup (Phase 0)

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. (optional) configure environment
copy .env.example .env

# 4. Run
python run.py
```

You should see a window confirming the app launched, Urdu renders RTL, and the
database connection succeeded.

## Database migrations (Alembic)

Alembic is the source of truth for the schema.

```powershell
# Apply all pending migrations (also: python -m timber.db.init_db)
python -m alembic upgrade head

# After changing a model, create a new migration, then apply it
python -m alembic revision --autogenerate -m "describe the change"
python -m alembic upgrade head

# Roll back the most recent migration
python -m alembic downgrade -1
```

## Build phases

| Phase | Work | Status |
|---|---|---|
| 0 | Setup & structure | ✅ done |
| 1 | Database models + Alembic migrations | ✅ done |
| 2 | Core logic (auth, calculations, balances) | ✅ done |
| 3 | Entry screens (quick/bapari/factory/combined/payment) | ✅ done |
| 4 | Ledgers (7 views) | ✅ done |
| 5 | Dashboard & charts (Qt Charts) | ✅ done |
| 6 | Reports & PDF/Excel export | ✅ done |
| 7 | Search, backup, audit, bulk import, settings/management | ✅ done |
| 8 | Testing & hardening (logging, exception handler, 85 tests) | ✅ done |
| 9 | Packaging (.exe) + Urdu user guide | ⬜ |


desing the legger exaclty like this and remove outstanding columns 
 and we do paytement in status it only show bank it must show from which bank it decuted and to which account it go to supplier 
prorper bnak name if cash it show cash 

and in expenses cloulms freight is even visibnle properly set it and make possible for multiple lines 

and banlces must works like i show the ledger for fatory and supplier legger 
for supplier either ledegr or any other page if balance is negative it mean we have to give that to suplier and if balnce is positive it means supllier should have to send that amount to us or send truks of woods whatever same like leger screenshot of client 

same like for factory balnce is negartive it means that amount factory hav eto sned us and 
mmake it possible and opening balace is directly link to our account either for supplier or facorty or our account opening balnce msut change means upadted balance 

do a smoke test to test it exaclty by putting same data of tehse two leger and send to any facortory and check if it working correclty 


one more for all proejct while we do new enteri and new row at any page make it for all project that new enetry or new row must shown above the old not below the old row for pages



C:\src\flutter\bin\flutter.bat run -d chrome --dart-define=API_URL=http://127.0.0.1:8000


uvicorn timber.api.main:app --host 0.0.0.0 --port 8000, and web → python -m http.server 8080 --bind 0.0.0.0 --directory build/web (from the mobile folder).