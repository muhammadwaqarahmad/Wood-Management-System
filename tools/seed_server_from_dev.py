"""Replace the server's master data with the DEV database's master data.

Fresh-start seed, authorised by the client. Copies suppliers, factories and
wood types from the local dev SQLite DB into the live server Postgres:

  * opening balances forced to 0
  * wood-type rates forced to 0 (per requirement: "no rates set")
  * bilingual English/Urdu names preserved

Because the server's current parties/wood-types are referenced by its 32 trades
+ 1 payment, those transactions are cleared too (fresh start). Users, bank
accounts, locations, translations and the audit log are KEPT. A full JSON backup
was taken first (tools/backup_server_json.py).

Everything runs in ONE transaction — any error rolls the whole thing back.

    python tools/seed_server_from_dev.py            # do it
    python tools/seed_server_from_dev.py --dry-run  # show the plan only
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

DRY = "--dry-run" in sys.argv
ROOT = Path(__file__).resolve().parent.parent

# --- dev engine (SQLite) — resolve BEFORE loading the server env -------------
DEV_DB = ROOT / "storage" / "timber.db"
DEV_URL = f"sqlite:///{DEV_DB}"

# --- load server connection (never printed) ---------------------------------
for line in (ROOT / "deploy" / "CLIENT-PC.env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip().strip('"').strip("'")

import timber.config as config
from sqlalchemy import MetaData, create_engine, func, select
from sqlalchemy.orm import Session

from timber.core import admin_service
from timber.db.models import Party, WoodType
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.seed_master import ensure_unknown_parties

SERVER_URL = config.database_url()

# Tables to PRESERVE on the server; everything else is cleared for the fresh start.
KEEP = {
    "users", "bank_accounts", "translations", "audit_log", "locations",
    "alembic_version", "app_settings", "settings",
}


def main() -> int:
    dev_eng = create_engine(DEV_URL)
    srv_eng = create_engine(SERVER_URL, pool_pre_ping=True)

    # 1) read dev master data
    with Session(dev_eng) as ds:
        suppliers = [(p.name_en, p.name_ur) for p in ds.scalars(
            select(Party).where(Party.party_type == PARTY_BAPARI).order_by(Party.id))]
        factories = [(p.name_en, p.name_ur) for p in ds.scalars(
            select(Party).where(Party.party_type == PARTY_FACTORY).order_by(Party.id))]
        woods = [w.name for w in ds.scalars(select(WoodType).order_by(WoodType.id))]

    print("=" * 60)
    print(f"SOURCE (dev): {len(suppliers)} suppliers, {len(factories)} factories, "
          f"{len(woods)} wood types")
    print(f"TARGET (server): {config.PG_HOST}:{config.PG_PORT}/{config.PG_DB}")
    print("=" * 60)

    md = MetaData()
    md.reflect(bind=srv_eng)
    to_clear = [t for t in reversed(md.sorted_tables) if t.name not in KEEP]
    print("\nWill CLEAR (fresh start):", ", ".join(t.name for t in to_clear))
    print("Will KEEP             :", ", ".join(sorted(
        t.name for t in md.sorted_tables if t.name in KEEP)))

    if DRY:
        print("\n--dry-run: nothing changed.")
        return 0

    with Session(srv_eng) as ss:
        try:
            # 2) clear (child tables first — reversed dependency order)
            for t in to_clear:
                n = ss.execute(t.delete()).rowcount
                if n:
                    print(f"  cleared {t.name:20} {n}")

            # 3) insert master data (balances 0, wood rates 0, bilingual names kept)
            for en, ur in suppliers:
                admin_service.create_party(
                    ss, name_en=en, name_ur=ur, party_type=PARTY_BAPARI,
                    opening_balance=0)
            for en, ur in factories:
                admin_service.create_party(
                    ss, name_en=en, name_ur=ur, party_type=PARTY_FACTORY,
                    opening_balance=0)
            for name in woods:
                ss.add(WoodType(name=name, default_supplier_rate=0,
                                default_factory_rate=0))
            ss.flush()
            ensure_unknown_parties(ss)   # guarantee the Unknown placeholders
            ss.commit()
        except Exception:
            ss.rollback()
            print("\nERROR — rolled back, server unchanged.")
            raise

    # 4) verify
    with Session(srv_eng) as ss:
        n_sup = ss.scalar(select(func.count(Party.id)).where(Party.party_type == PARTY_BAPARI))
        n_fac = ss.scalar(select(func.count(Party.id)).where(Party.party_type == PARTY_FACTORY))
        n_wood = ss.scalar(select(func.count(WoodType.id)))
        nz_bal = ss.scalar(select(func.count(Party.id)).where(Party.opening_balance != 0))
        nz_rate = ss.scalar(select(func.count(WoodType.id)).where(
            (WoodType.default_supplier_rate != 0) | (WoodType.default_factory_rate != 0)))
    print("\n" + "=" * 60)
    print("DONE — server now has:")
    print(f"  suppliers : {n_sup}   (incl. Unknown supplier)")
    print(f"  factories : {n_fac}   (incl. Unknown factory)")
    print(f"  wood types: {n_wood}")
    print(f"  non-zero opening balances : {nz_bal}   (want 0)")
    print(f"  wood types with a rate    : {nz_rate}   (want 0)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
