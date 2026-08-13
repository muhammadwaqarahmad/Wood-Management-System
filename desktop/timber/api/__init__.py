"""HTTP API for the mobile app.

A thin FastAPI layer over the SAME ``timber.core`` the desktop uses — so the
phone and the desktop can never disagree about money. It runs as a SEPARATE
process next to the database on the server (never inside the desktop exe), so
its queries are local and fast; the phone makes one request and gets one answer.

Read-only in this first phase (dashboard, balances, ledgers, trades). Writes
(payments, then full entry) come later, going through the same core services
the desktop calls.

Run it:   python -m timber.api        (reads the same .env as the desktop)
"""
