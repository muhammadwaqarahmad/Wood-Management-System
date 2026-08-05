"""API configuration — read from the environment (same .env as the desktop)."""
from __future__ import annotations

import logging
import os
import secrets

log = logging.getLogger("timber.api")

# Secret used to sign login tokens. MUST be set in production (put a long random
# value in the server's .env as TIMBER_API_SECRET) so tokens survive restarts
# and can't be forged. If unset we generate a throwaway one and warn — fine for
# local testing, but every restart then invalidates existing logins.
API_SECRET: str = os.getenv("TIMBER_API_SECRET", "").strip()
if not API_SECRET:
    API_SECRET = secrets.token_urlsafe(48)
    log.warning("TIMBER_API_SECRET not set — using a throwaway secret; set one "
                "in the server .env for production.")

# Access token: short-lived, sent with every request.
ACCESS_TTL_HOURS: int = int(os.getenv("TIMBER_API_ACCESS_HOURS", "12"))
# Refresh token: long-lived, stored in the phone's hardware keystore and used
# (after a biometric unlock) to mint fresh access tokens without re-typing the
# password. Rotated on every use.
REFRESH_TTL_DAYS: int = int(os.getenv("TIMBER_API_REFRESH_DAYS", "45"))

# Which origins may call the API from a browser. The native app doesn't need
# CORS, but the party web-portal (later) will. "*" is fine while it's read-only
# behind token auth; tighten to the portal's domain when that ships.
CORS_ORIGINS: list[str] = [
    o.strip() for o in os.getenv("TIMBER_API_CORS", "*").split(",") if o.strip()
]

PORT: int = int(os.getenv("TIMBER_API_PORT", "8000"))
