"""Wipe ALL business data, keeping only the admin login (and the schema).

Use this to give the client a clean start. The next app launch re-seeds the
master data (suppliers / factories / bank accounts) from ``seed_master``.

    # this PC's local database
    ./.venv/Scripts/python.exe scripts/reset_data.py --yes

    # the shared PostgreSQL server (run from a PC that can reach it)
    TIMBER_DB_BACKEND=postgresql TIMBER_PG_HOST=192.168.10.35 \
    TIMBER_PG_DB=timber TIMBER_PG_USER=timber TIMBER_PG_PASSWORD=... \
        ./.venv/Scripts/python.exe scripts/reset_data.py --yes

Nothing is deleted without --yes.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select  # noqa: E402

from timber.db.engine import SessionLocal, engine  # noqa: E402
from timber.db.models import (  # noqa: E402
    AccountTransfer,
    AuditLog,
    BankAccount,
    BapariTxn,
    CombinedTxn,
    Expense,
    FactoryTxn,
    Loan,
    LoanRepayment,
    Party,
    PartyBank,
    PartyPhone,
    Payment,
    PaymentAllocation,
    TradeKey,
    UnknownPayment,
    User,
)

# Child rows first: every table that references another must be cleared
# before its parent, or the delete hits a foreign-key error.
_ORDER = [
    TradeKey,
    UnknownPayment,
    PaymentAllocation,
    CombinedTxn,
    Expense,
    LoanRepayment,
    Loan,
    AccountTransfer,
    Payment,
    BapariTxn,
    FactoryTxn,
    PartyPhone,
    PartyBank,
    Party,
    BankAccount,
    AuditLog,
]


def main() -> int:
    if "--yes" not in sys.argv:
        print(__doc__)
        print(f"Target database: {engine.url.render_as_string(hide_password=True)}")
        print("\nRefusing to delete without --yes.")
        return 1

    print(f"Target database: {engine.url.render_as_string(hide_password=True)}")
    with SessionLocal() as session:
        # party_links is a plain association table (no ORM class).
        from timber.db.models.party_link import party_links

        session.execute(delete(party_links))
        for model in _ORDER:
            n = session.scalar(select(func.count()).select_from(model))
            session.execute(delete(model))
            if n:
                print(f"  cleared {model.__tablename__:<22} {n}")
        users = session.scalar(select(func.count(User.id)))
        session.commit()
        print(f"\nKept {users} user(s). All business data removed.")
    print("Next app launch will re-seed suppliers / factories / bank accounts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
