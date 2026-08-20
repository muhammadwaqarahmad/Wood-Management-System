"""The FastAPI application: wires the routers and CORS together."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from timber import __version__, config
from timber.api import settings
from timber.api.deps import get_session
from timber.api.routers import (
    audit,
    auth,
    backup,
    dashboard,
    ledgers,
    master,
    money,
    parties,
    payments,
    reports,
    search,
    trades,
    users,
)

_log = logging.getLogger("timber.api")

# Captures any startup migration/seed failure so it can be surfaced by /ready
# (Railway logs aren't always at hand; this makes the failure visible over HTTP).
_startup_error: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bring the (cloud) database schema up to head before serving.

    The API queries columns/tables that Alembic migrations add (e.g.
    payments.entry_date, factory_split_rates). A code deploy does NOT run
    migrations by itself, so without this a fresh deploy would 500 on those
    endpoints until someone migrated the DB by hand. Running ``alembic upgrade
    head`` here (same self-migrate pattern the desktop uses, targeting whatever
    TIMBER_PG_* points at) keeps schema and code in lock-step on every deploy.
    It is idempotent — a no-op once the DB is already at head — and guarded so a
    migration hiccup logs loudly but never takes the whole API offline.
    """
    try:
        from timber.db.init_db import upgrade_to_head

        upgrade_to_head()
        # Seed the default admin on a brand-new database. The desktop does this
        # on first run (app.py); the API must too, or a fresh cloud DB has no
        # user to log in with. Idempotent — a no-op once any user exists.
        from timber.db.engine import SessionLocal
        from timber.db.seed import ensure_admin

        with SessionLocal() as session:
            ensure_admin(session)
    except Exception as exc:  # noqa: BLE001 - never let a migration/seed error kill the API
        global _startup_error
        _startup_error = f"{type(exc).__name__}: {exc}"
        _log.exception("Startup DB migration/seed failed; serving with current schema")
    yield


app = FastAPI(
    title="Abdul Sattar Woods API",
    version=__version__,
    description="Read-only mobile API over the same accounting core as the "
                "desktop app.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audit.router)
app.include_router(auth.router)
app.include_router(backup.router)
app.include_router(dashboard.router)
app.include_router(ledgers.router)
app.include_router(master.router)
app.include_router(money.router)
app.include_router(parties.router)
app.include_router(payments.router)
app.include_router(reports.router)
app.include_router(search.router)
app.include_router(trades.router)
app.include_router(users.router)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Liveness check — no auth, no DB. Confirms the API process is up."""
    return {
        "ok": True,
        "app": config.APP_NAME,
        "version": __version__,
        "backend": config.DB_BACKEND,
    }


@app.get("/ping", tags=["meta"])
def ping(session: Session = Depends(get_session)) -> dict:
    """Keep-alive that runs a real DB query (SELECT 1). Pinging this every ~10
    minutes keeps the Render service awake AND keeps the Supabase project active
    (a free Supabase project auto-pauses after ~7 days with no connections)."""
    session.execute(text("SELECT 1"))
    return {"ok": True, "db": "up"}


@app.get("/ready", tags=["meta"])
def ready() -> dict:
    """Deploy diagnostic (no auth): did the startup migration + admin seed run?
    Surfaces the real reason a fresh deploy 500s on login without needing the
    host's logs. Safe to leave in — it exposes no data, only schema readiness."""
    from sqlalchemy import func, select

    from timber.db.engine import SessionLocal
    from timber.db.models import User

    out: dict = {"startup_error": _startup_error}
    try:
        with SessionLocal() as s:
            out["users_table"] = "ok"
            out["user_count"] = s.scalar(select(func.count()).select_from(User))
            out["admin_exists"] = (
                s.scalar(select(User).where(User.username == "admin")) is not None
            )
    except Exception as exc:  # noqa: BLE001 - the point is to REPORT the error
        out["users_table"] = f"{type(exc).__name__}: {exc}"
    return out
