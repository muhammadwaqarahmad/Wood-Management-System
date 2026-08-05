"""SQLAlchemy engine, session factory, and declarative base.

Phase 0 sets up the connection plumbing only. ORM models arrive in
Phase 1 and will subclass ``Base`` defined here.
"""

from __future__ import annotations

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from timber import config

# Make sure storage dirs exist before SQLite tries to open its file.
config.ensure_dirs()

# Connection-resilience options. The desktop app is long-lived and hits the DB
# from two threads (the PyQt UI + the embedded FastAPI/uvicorn server), so
# pooled connections can go stale between uses — the PC sleeps, PostgreSQL
# times out an idle connection, or the network blips. Without a guard the pool
# hands out a dead socket and psycopg raises "server closed the connection
# unexpectedly" mid-query. `pool_pre_ping` cheaply checks each connection and
# transparently reconnects a dead one; a short `pool_recycle` retires a
# connection before a router/firewall/server idle timeout can kill it.
#
# IMPORTANT: do NOT pass libpq TCP-keepalive params (keepalives / keepalives_idle
# / keepalives_interval / keepalives_count) here. `keepalives_count` needs the
# TCP_KEEPCNT socket option, which OLDER WINDOWS lacks — and libpq then FAILS
# THE WHOLE CONNECTION ("could not connect / socket is not connected") instead
# of ignoring it. That broke a client PC on first launch. `pool_pre_ping` +
# `pool_recycle` give portable stale-connection protection with no OS-specific
# socket options, so they work on every Windows version.
_engine_kwargs: dict = {"echo": False, "future": True, "pool_pre_ping": True}
if config.DB_BACKEND == "postgresql":
    _engine_kwargs["pool_recycle"] = 280  # retire a connection before ~5 min idle-drop
    # Server-side statement timeout so a stuck query can't hang the UI forever.
    # This is a session GUC (portable, no OS socket options), applied only to
    # THIS app engine — alembic uses its own engine, so migrations are exempt.
    _stmt_ms = config.PG_STATEMENT_TIMEOUT.strip()
    if _stmt_ms and _stmt_ms != "0":
        _engine_kwargs["connect_args"] = {
            "options": f"-c statement_timeout={_stmt_ms}"
        }

engine = create_engine(config.database_url(), **_engine_kwargs)

# SQLite tuning for years of daily entries: WAL journalling (readers never
# block the writer), relaxed-but-safe sync, and a bigger page cache.
if engine.url.get_backend_name() == "sqlite":
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA cache_size=-20000")     # ~20 MB
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.close()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)

# Naming convention so all constraints get explicit names. This is what
# lets Alembic perform ALTERs on SQLite (batch mode rebuilds tables and
# needs named constraints).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Shared declarative base for all ORM models.
Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))


def check_connection() -> tuple[bool, str]:
    """Probe the database with ``SELECT 1``. Returns (ok, message)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, f"Database connected ({engine.url.get_backend_name()})"
    except Exception as exc:  # noqa: BLE001 - surface any driver error to the UI
        return False, f"Database connection failed: {exc}"


def is_connected() -> bool:
    """Cheap boolean form of :func:`check_connection` for background polling."""
    return check_connection()[0]


def reset_pool() -> None:
    """Throw away every pooled connection so the next use dials a brand-new
    one. Call this after a detected disconnect: it stops recovery from waiting
    on a dead/half-open socket and makes the next connect honour the short
    ``connect_timeout`` instead of the OS's minutes-long TCP timeout."""
    engine.dispose()


def warm_pool(n: int = 3) -> None:
    """Open a few authenticated connections up front so they sit warm in the
    pool. On a cloud database the first connect pays a ~2-4s TLS + pooler
    handshake; doing that in the BACKGROUND at startup means the user's first
    action (the dashboard right after login) reuses a ready connection instead
    of freezing on that handshake. Best-effort — never raises.

    We open all ``n`` at once (so they are distinct connections, not the same
    one reused) then return them to the pool, where QueuePool keeps them open
    for reuse by either thread (the PyQt UI + the embedded FastAPI server)."""
    conns = []
    try:
        for _ in range(n):
            c = engine.connect()
            c.execute(text("SELECT 1"))
            conns.append(c)
    except Exception:  # noqa: BLE001 - warming is optional
        pass
    finally:
        for c in conns:
            try:
                c.close()  # returns to the pool kept-alive (not disposed)
            except Exception:  # noqa: BLE001
                pass
