"""The FastAPI application: wires the routers and CORS together."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from timber import __version__, config
from timber.api import settings
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
    """Liveness check — no auth. Confirms the API is up and which DB it uses."""
    return {
        "ok": True,
        "app": config.APP_NAME,
        "version": __version__,
        "backend": config.DB_BACKEND,
    }
