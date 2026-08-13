"""Full read-only backup of the live server DB to a timestamped JSON file.

A safety net taken BEFORE any destructive master-data reset. Dumps every table
(all rows) so the exact pre-change state can be restored/inspected if needed.
Never prints the password.

    python tools/backup_server_json.py [env_file]
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_env(path: Path) -> None:
    import os
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _json_default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


def main() -> int:
    env = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parent.parent / "deploy" / "CLIENT-PC.env"
    load_env(env)

    import timber.config as config
    from sqlalchemy import MetaData, create_engine, select

    eng = create_engine(config.database_url(), pool_pre_ping=True)
    md = MetaData()
    md.reflect(bind=eng)

    out = {}
    counts = {}
    with eng.connect() as conn:
        for name, table in md.tables.items():
            rows = [dict(r._mapping) for r in conn.execute(select(table))]
            out[name] = rows
            counts[name] = len(rows)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = Path(__file__).resolve().parent.parent / "storage" / "backups"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"server_backup_{stamp}.json"
    path.write_text(json.dumps(out, default=_json_default, ensure_ascii=False, indent=1),
                    encoding="utf-8")

    print("SERVER BACKUP WRITTEN")
    print(f"  file : {path}")
    print(f"  size : {path.stat().st_size/1024:.0f} KB")
    print("  rows per table:")
    for n in sorted(counts):
        if counts[n]:
            print(f"    {n:22} {counts[n]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
