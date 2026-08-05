"""The FastAPI application: wires the routers and CORS together."""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from timber import __version__, config
from timber.api import settings
from timber.api.deps import get_session
from timber.api.routers import (
    auth,
    dashboard,
    ledgers,
    master,
    money,
    parties,
    payments,
    reports,
    search,
    trades,
)

app = FastAPI(
    title="Abdul Sattar Woods API",
    version=__version__,
    description="Read-only mobile API over the same accounting core as the "
                "desktop app.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(ledgers.router)
app.include_router(master.router)
app.include_router(money.router)
app.include_router(parties.router)
app.include_router(payments.router)
app.include_router(reports.router)
app.include_router(search.router)
app.include_router(trades.router)


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
