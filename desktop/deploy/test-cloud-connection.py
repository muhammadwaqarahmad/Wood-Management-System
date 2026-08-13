r"""Time the round-trip latency to the cloud (Supabase) database, using the SAME
psycopg driver the app uses. Runs anywhere the project venv exists -- no psql,
no PostgreSQL install needed. Nothing is written to the database.

Usage (from the project folder, one line):
  .\.venv\Scripts\python.exe deploy\test-cloud-connection.py --env "dist\Abdul Sattar Woods\.env"
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def load_env(path: str) -> dict[str, str]:
    cfg: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        cfg[key.strip()] = val.strip()
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True, help="path to the .env with TIMBER_PG_* values")
    args = ap.parse_args()

    cfg = load_env(args.env)
    host = cfg.get("TIMBER_PG_HOST", "")
    port = cfg.get("TIMBER_PG_PORT", "5432")
    user = cfg.get("TIMBER_PG_USER", "")
    pw = cfg.get("TIMBER_PG_PASSWORD", "")
    db = cfg.get("TIMBER_PG_DB", "postgres")
    ssl = cfg.get("TIMBER_PG_SSLMODE", "require") or "require"

    if not host or not user or not pw or pw.startswith("PASTE"):
        print("Fill in TIMBER_PG_HOST / TIMBER_PG_USER / TIMBER_PG_PASSWORD in the .env first.")
        return 1

    import psycopg

    conninfo = (
        f"host={host} port={port} dbname={db} user={user} password={pw} "
        f"sslmode={ssl} connect_timeout=8"
    )
    print(f"Connecting to {host}:{port}  db={db}  user={user}  ssl={ssl} ...")
    try:
        t0 = time.perf_counter()
        with psycopg.connect(conninfo) as conn:
            connect_ms = (time.perf_counter() - t0) * 1000
            print(f"Connected OK in {connect_ms:.0f} ms")
            times: list[float] = []
            with conn.cursor() as cur:
                for _ in range(10):
                    s = time.perf_counter()
                    cur.execute("select 1")
                    cur.fetchone()
                    times.append((time.perf_counter() - s) * 1000)
    except Exception as exc:  # noqa: BLE001 - report clearly instead of a traceback
        print("FAILED to connect:")
        print(f"  {exc}")
        print("Check: password correct? pooler host + session port 5432? sslmode=require? internet up?")
        return 1

    avg = sum(times) / len(times)
    print(
        f"\nRound-trip latency over 10 queries:  avg {avg:.0f}ms  "
        f"(min {min(times):.0f}ms, max {max(times):.0f}ms)"
    )
    if avg < 150:
        print("=> Excellent.")
    elif avg < 400:
        print("=> Great for a shared cloud DB. Roll out to the other PCs.")
    elif avg < 800:
        print("=> Fine for daily use (the app batches each page to ~one round-trip).")
    else:
        print("=> High -- check Wi-Fi/ISP, or reconsider the region.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
