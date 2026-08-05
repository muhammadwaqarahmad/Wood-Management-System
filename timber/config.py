"""Application configuration.

Switching between SQLite (single PC / development) and PostgreSQL
(LAN / production) is ONE line: change ``DB_BACKEND`` below, or set the
``TIMBER_DB_BACKEND`` environment variable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# When packaged with PyInstaller, ``sys.frozen`` is set. Writable runtime
# data (sqlite db, backups, reports, logs, .env, settings.json) must live
# NEXT TO THE .EXE — never inside the read-only bundle. Read-only bundled
# data (alembic migrations, fonts) lives in the PyInstaller temp dir
# (``sys._MEIPASS``).
_FROZEN = getattr(sys, "frozen", False)
if _FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent      # holds the writable data
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))  # read-only bundled data
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = APP_DIR

# Kept for backwards-compatibility (older code referenced PROJECT_ROOT).
PROJECT_ROOT = APP_DIR

# Load a .env file from next to the app if present (optional).
load_dotenv(APP_DIR / ".env")

# Runtime data lives outside the package so it stays writable when
# bundled into a .exe (sqlite db, backups, generated reports, logs).
STORAGE_DIR = APP_DIR / "storage"
BACKUP_DIR = STORAGE_DIR / "backups"
REPORTS_DIR = STORAGE_DIR / "reports"
LOG_DIR = STORAGE_DIR / "logs"

# Schema migrations (bundled as data when frozen so the app can self-migrate).
ALEMBIC_INI = BUNDLE_DIR / "alembic.ini"
ALEMBIC_DIR = BUNDLE_DIR / "alembic"

# Bundled assets (fonts, icons, stylesheets).
RESOURCES_DIR = BUNDLE_DIR / "timber" / "resources"
FONTS_DIR = RESOURCES_DIR / "fonts"

# ---------------------------------------------------------------------------
# Database  ◀── flip this one line to switch backends
# ---------------------------------------------------------------------------
DB_BACKEND = os.getenv("TIMBER_DB_BACKEND", "sqlite")  # "sqlite" | "postgresql"

# SQLite (development / single PC)
SQLITE_PATH = STORAGE_DIR / "timber.db"

# PostgreSQL (production / LAN — main PC holds the server)
PG_HOST = os.getenv("TIMBER_PG_HOST", "192.168.1.100")
PG_PORT = os.getenv("TIMBER_PG_PORT", "5432")
PG_USER = os.getenv("TIMBER_PG_USER", "timber")
PG_PASSWORD = os.getenv("TIMBER_PG_PASSWORD", "")
PG_DB = os.getenv("TIMBER_PG_DB", "timber")
# TLS mode. Supabase (and any cloud Postgres) REQUIRES SSL — set "require"
# (or "verify-full" with a CA cert) in the .env. Empty = let psycopg decide
# (its default is "prefer", which still uses SSL when the server offers it),
# so a plain LAN Postgres keeps working unchanged.
PG_SSLMODE = os.getenv("TIMBER_PG_SSLMODE", "").strip()
# Seconds to wait for the server before giving up. Without this a client PC
# that is off the office Wi-Fi (or whose server is off) sits frozen on the
# OS's long TCP timeout instead of reporting the problem straight away.
PG_CONNECT_TIMEOUT = os.getenv("TIMBER_PG_CONNECT_TIMEOUT", "5")

# Server-side cap (milliseconds) on any single statement, so a stuck query
# (lock contention, a runaway scan) can never hang the UI thread forever — it
# aborts with a clear error instead. "0" disables it. Migrations run on their
# OWN engine (alembic env.py), so this never interrupts a long migration.
PG_STATEMENT_TIMEOUT = os.getenv("TIMBER_PG_STATEMENT_TIMEOUT", "30000")

# How many days of audit-log history to keep. Older entries are pruned
# automatically on each app launch. "0" keeps everything (no pruning).
AUDIT_RETENTION_DAYS = os.getenv("TIMBER_AUDIT_RETENTION_DAYS", "3")

# Whether the app AUTO-SEEDS the client's supplier/factory/bank-account master
# data on a fresh, empty database. OFF by default now that the live data lives
# in the shared cloud database — a new PC/exe connects to it instead of loading
# its own copy. The admin login, the Cash account, and the Unknown-party
# placeholders are always ensured (the app needs them) regardless of this flag.
# To seed a brand-new cloud DB once, run:  python -m timber.db.seed_master
SEED_MASTER_DATA = os.getenv("TIMBER_SEED_MASTER_DATA", "0").strip().lower() in (
    "1", "true", "yes", "on",
)


def database_url() -> str:
    """Return the SQLAlchemy connection URL for the active backend."""
    if DB_BACKEND == "postgresql":
        from urllib.parse import quote_plus

        url = (
            f"postgresql+psycopg://{quote_plus(PG_USER)}:{quote_plus(PG_PASSWORD)}"
            f"@{PG_HOST}:{PG_PORT}/{PG_DB}"
            f"?connect_timeout={PG_CONNECT_TIMEOUT}"
        )
        if PG_SSLMODE:  # e.g. "require" for Supabase / any cloud Postgres
            url += f"&sslmode={PG_SSLMODE}"
        return url
    return f"sqlite:///{SQLITE_PATH}"


def ensure_dirs() -> None:
    """Create runtime directories if they do not exist."""
    for path in (STORAGE_DIR, BACKUP_DIR, REPORTS_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
# The business/brand name — the SINGLE source of truth for what the app calls
# itself everywhere it is shown (window title, login, sidebar brand, dashboard,
# "we paid" label, and the embedded web pages, which receive it as a URL param).
# Override it per-install from the .env next to the exe without touching code:
#     TIMBER_BUSINESS_NAME=Your Business Name
#     TIMBER_BUSINESS_NAME_UR=آپ کے کاروبار کا نام
# NOTE: the installed folder / .exe / Start-menu name are baked at BUILD time by
# the installer (AbdulSattarWoods.iss #define AppName) — those can't read .env,
# so keep the two in sync when you rebrand.
APP_NAME = os.getenv("TIMBER_BUSINESS_NAME", "Abdul Sattar Woods")
APP_NAME_UR = os.getenv("TIMBER_BUSINESS_NAME_UR", "عبدالستار ووڈز")
DEFAULT_LANGUAGE = os.getenv("TIMBER_LANG", "ur")  # "ur" | "en"

# Live translation of English free-text data for Urdu users (needs internet).
# Set TIMBER_TRANSLATE=off to disable (data then shows exactly as typed).
TRANSLATE_ENABLED = os.getenv("TIMBER_TRANSLATE", "on").lower() not in (
    "0", "off", "false", "no",
)
TRANSLATE_TARGET = "ur"
