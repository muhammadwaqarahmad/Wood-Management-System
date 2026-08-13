"""Phase 0 — find payments whose direction is the reverse of its party type.

Before the direction fix, the party ledger subtracted EVERY payment regardless
of direction, so a reverse-direction row (money received from a supplier, or
paid out to a factory) moved that party's balance the wrong way by twice the
amount. The only way such a row could be created in the shipped app was
Unknown -> Claim onto a supplier, which always writes direction="in".

This script only READS. It prints the affected parties and the correction each
balance needs. Run it on the machine that holds the live database:

    python tools/check_payment_directions.py

No credentials are printed.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

import timber.config as config
from timber.db.engine import SessionLocal
from timber.db.models import Party, Payment
from timber.db.models.party import PARTY_BAPARI
from timber.db.models.payment import PAYMENT_IN, PAYMENT_OUT


def natural_direction(party_type: str) -> str:
    """The direction a party's payments normally flow in."""
    return PAYMENT_OUT if party_type == PARTY_BAPARI else PAYMENT_IN


def main() -> int:
    print("=" * 78)
    print("PAYMENT DIRECTION CHECK")
    print(f"backend: {config.DB_BACKEND}")
    print("=" * 78)

    with SessionLocal() as session:
        rows = session.execute(
            select(Payment, Party)
            .join(Party, Payment.party_id == Party.id)
            .where(Payment.is_void.is_(False))
            .order_by(Payment.txn_date, Payment.id)
        ).all()

        suspect = [
            (p, party) for p, party in rows
            if p.direction != natural_direction(party.party_type)
        ]

        print(f"\npayments scanned : {len(rows)}")
        print(f"reverse-direction: {len(suspect)}")

        if not suspect:
            print("\nNo reverse-direction payments. No balances are affected.")
            return 0

        print("\nThese rows moved their party's balance the WRONG WAY.")
        print("Each balance is off by 2x the amount (it was subtracted when it")
        print("should have been added, or the reverse).\n")

        per_party: dict[int, tuple[str, Decimal]] = {}
        print(f"{'date':<12}{'party':<28}{'type':<10}{'dir':<6}{'amount':>14}")
        print("-" * 78)
        for p, party in suspect:
            print(f"{str(p.txn_date):<12}{party.name[:26]:<28}"
                  f"{party.party_type:<10}{p.direction:<6}{p.amount:>14,.2f}")
            name, tot = per_party.get(party.id, (party.name, Decimal("0")))
            per_party[party.id] = (name, tot + Decimal(str(p.amount)))

        print("\nCorrection needed per party (add this to the stored balance):")
        print("-" * 78)
        for _pid, (name, tot) in sorted(per_party.items(), key=lambda kv: kv[1][0]):
            print(f"  {name[:40]:<42}{tot * 2:>16,.2f}")

        print("\nAfter the direction fix is deployed these balances correct")
        print("themselves — the fix changes how they are COMPUTED, and nothing")
        print("here needs editing by hand. This list is for verification: the")
        print("named parties are the ones whose totals should visibly change.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
