"""READ-ONLY inspection of the live server database. Writes nothing.

Loads a server env file (default deploy/CLIENT-PC.env), connects, and reports
what master data + transactions already exist — so we can plan a safe seed
without guessing. Never prints the password.

    python tools/inspect_server.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def load_env(path: Path) -> None:
    import os
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def main() -> int:
    env = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parent.parent / "deploy" / "CLIENT-PC.env"
    load_env(env)

    import timber.config as config
    from sqlalchemy import create_engine, func, select, text

    print("=" * 66)
    print(f"SERVER INSPECTION (read-only) via {env.name}")
    print(f"backend {config.DB_BACKEND}  host {config.PG_HOST}:{config.PG_PORT}"
          f"  db {config.PG_DB}")
    print("=" * 66)

    engine = create_engine(config.database_url(), pool_pre_ping=True)
    from timber.db.models import (
        BankAccount, BapariTxn, CombinedTxn, Expense, FactoryTxn, Party,
        Payment, WoodType,
    )
    from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        rev = None
        try:
            rev = s.execute(text("select version_num from alembic_version")).scalar()
        except Exception:
            pass
        print(f"\nschema migration : {rev}")

        n_sup = s.scalar(select(func.count(Party.id)).where(Party.party_type == PARTY_BAPARI))
        n_fac = s.scalar(select(func.count(Party.id)).where(Party.party_type == PARTY_FACTORY))
        n_wood = s.scalar(select(func.count(WoodType.id)))
        n_acct = s.scalar(select(func.count(BankAccount.id)))
        print(f"suppliers        : {n_sup}")
        print(f"factories        : {n_fac}")
        print(f"wood types       : {n_wood}")
        print(f"bank accounts    : {n_acct}")

        # DEPENDENT DATA — the deciding factor for whether parties can be deleted
        n_bt = s.scalar(select(func.count(BapariTxn.id)))
        n_ft = s.scalar(select(func.count(FactoryTxn.id)))
        n_ct = s.scalar(select(func.count(CombinedTxn.id)))
        n_pay = s.scalar(select(func.count(Payment.id)))
        n_exp = s.scalar(select(func.count(Expense.id)))
        print(f"\n--- transactions already entered (matters before any delete) ---")
        print(f"purchase loads   : {n_bt}")
        print(f"sale loads       : {n_ft}")
        print(f"combined trades  : {n_ct}")
        print(f"payments         : {n_pay}")
        print(f"expenses         : {n_exp}")
        has_txns = any((n_bt, n_ft, n_ct, n_pay, n_exp))
        print(f"\n>>> dependent transactions exist: "
              f"{'YES — deleting parties is NOT safe' if has_txns else 'no — parties can be cleared safely'}")

        # non-zero opening balances / wood rates (the user wants all zero)
        nz_bal = s.scalar(select(func.count(Party.id)).where(Party.opening_balance != 0))
        print(f"\nparties with non-zero opening balance : {nz_bal}")
        try:
            nz_rate = s.scalar(select(func.count(WoodType.id)).where(
                (WoodType.default_supplier_rate != 0) | (WoodType.default_factory_rate != 0)))
            print(f"wood types with a rate set            : {nz_rate}")
        except Exception as exc:
            print(f"wood types rate check: (columns missing? {exc})")

        # show what's actually there so we can compare to seed_master.py
        print("\n--- current suppliers (up to 60) ---")
        for p in s.scalars(select(Party).where(Party.party_type == PARTY_BAPARI)
                           .order_by(Party.id).limit(60)):
            print(f"  #{p.id:<4} {p.name!r}  open={p.opening_balance}")
        print("\n--- current factories (up to 60) ---")
        for p in s.scalars(select(Party).where(Party.party_type == PARTY_FACTORY)
                           .order_by(Party.id).limit(60)):
            print(f"  #{p.id:<4} {p.name!r}  open={p.opening_balance}")
        print("\n--- current wood types ---")
        for w in s.scalars(select(WoodType).order_by(WoodType.id)):
            print(f"  #{w.id:<4} {w.name!r}")

    print("\n(read-only — nothing was changed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
