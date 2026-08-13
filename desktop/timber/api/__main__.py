"""Run the API:  python -m timber.api

Reads the SAME .env as the desktop, so on the server it connects to the local
PostgreSQL. Binds 0.0.0.0 so other devices on the LAN (and the Cloudflare
Tunnel) can reach it.
"""
from __future__ import annotations

import logging

import uvicorn

from timber.api import settings
from timber.core.logging_setup import setup_logging


def main() -> None:
    setup_logging()
    log = logging.getLogger("timber.api")
    log.info("Starting Abdul Sattar Woods API on port %d", settings.PORT)
    uvicorn.run(
        "timber.api.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
