"""Database-connection health helpers, shared by the app entry point and the
UI so a dropped connection is recognised and explained the same way everywhere.

Kept dependency-light (config + i18n only) so any layer can import it without
an import cycle.
"""

from __future__ import annotations

from timber import config, i18n

# Plain-language markers psycopg / libpq use when the SERVER IS UNREACHABLE
# (as opposed to a real query bug). We also match SQLAlchemy's typed errors.
_MARKERS = (
    "server closed the connection",
    "connection refused",
    "could not connect",
    "could not translate host",
    "consuming input failed",
    "terminating connection",
    "connection already closed",
    "connection is closed",
    "connection reset",
    "no connection to the server",
    "network is unreachable",
    "connection timed out",
    "timeout expired",
    "ssl connection has been closed",
    "connection failed",
)


def is_connection_error(exc: BaseException | None) -> bool:
    """True if ``exc`` means the DATABASE IS UNREACHABLE (server off, wrong
    Wi-Fi, network blip, dropped connection) rather than a real bug. Walks the
    whole cause/context chain because SQLAlchemy wraps the psycopg error."""
    from sqlalchemy.exc import (
        DBAPIError,
        DisconnectionError,
        InterfaceError,
        OperationalError,
    )

    seen: set[int] = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, (OperationalError, InterfaceError, DisconnectionError)):
            return True
        if isinstance(cur, DBAPIError) and getattr(cur, "connection_invalidated", False):
            return True
        if any(m in str(cur).lower() for m in _MARKERS):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def unreachable_message(*, with_retry_hint: bool = False) -> str:
    """Plain-language 'the database can't be reached' message. On PostgreSQL it
    also lists the server address and the two usual causes (server off / wrong
    Wi-Fi / changed address)."""
    if config.DB_BACKEND == "postgresql":
        msg = (
            f"{i18n.tr('db_unreachable')}\n\n"
            f"{i18n.tr('db_server_label')}: {config.PG_HOST}:{config.PG_PORT}\n\n"
            f"1.  {i18n.tr('db_check_server_on')}\n"
            f"2.  {i18n.tr('db_check_wifi')}\n"
            f"3.  {i18n.tr('db_check_env')}"
        )
    else:
        msg = i18n.tr("db_unreachable")
    if with_retry_hint:
        msg += f"\n\n{i18n.tr('db_try_again')}"
    return msg
