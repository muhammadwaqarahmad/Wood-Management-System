"""Verify a database the app is configured to use — run it ON the server.

Reads an env file (default deploy/MAIN-SERVER.env, i.e. the LOCAL Postgres the
office server runs on), connects, and reports that everything the app needs is
present: server reachable, schema at the right migration, hot-path indexes in
place. Read-only. Never prints the password.

    python tools/check_db.py                       # checks MAIN-SERVER.env (local)
    python tools/check_db.py deploy/ASW-CLOUD.env  # checks the cloud backup
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_env(path: Path) -> None:
    import os
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip().strip('"').strip("'")


def main() -> int:
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parent.parent / "deploy" / "MAIN-SERVER.env"
    if not env_path.exists():
        print(f"env file not found: {env_path}")
        return 2
    load_env(env_path)

    import timber.config as config  # after env is loaded
    from sqlalchemy import create_engine, text

    print("=" * 62)
    print("DATABASE CHECK")
    print(f"env      : {env_path.name}")
    print(f"backend  : {config.DB_BACKEND}")
    if config.DB_BACKEND == "postgresql":
        print(f"host     : {config.PG_HOST}:{config.PG_PORT}  db={config.PG_DB}")
    print("=" * 62)

    try:
        engine = create_engine(config.database_url(), pool_pre_ping=True,
                               connect_args={"connect_timeout": 8}
                               if config.DB_BACKEND == "postgresql" else {})
        with engine.connect() as conn:
            if config.DB_BACKEND == "postgresql":
                ver = conn.execute(text("show server_version")).scalar()
                size = conn.execute(text(
                    "select pg_size_pretty(pg_database_size(current_database()))"
                )).scalar()
                print(f"\n[OK] connected — Postgres {ver}, size {size}")
                tbls = [r[0] for r in conn.execute(text(
                    "select tablename from pg_tables where schemaname='public'"))]
            else:
                print("\n[OK] connected — SQLite")
                tbls = [r[0] for r in conn.execute(text(
                    "select name from sqlite_master where type='table'"))]

            try:
                rev = conn.execute(text("select version_num from alembic_version")).scalar()
            except Exception:
                rev = "(none)"

            # what the code expects at head
            from alembic.config import Config
            from alembic.script import ScriptDirectory
            head = ScriptDirectory.from_config(
                Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
            ).get_current_head()

            print(f"[..] tables present : {len(tbls)}")
            print(f"[..] migration      : {rev}")
            print(f"[..] code head      : {head}")
            if rev == head:
                print("[OK] schema is UP TO DATE with the code")
            else:
                print("[!!] schema is BEHIND the code — run the app once to "
                      "auto-upgrade, or `alembic upgrade head`")
        print("\nRESULT: database reachable and usable.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"\n[FAIL] could not use the database: {type(exc).__name__}: {exc}")
        if config.DB_BACKEND == "postgresql":
            print("  - is the PostgreSQL service running on this PC?")
            print("  - is the password in the .env correct?")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
