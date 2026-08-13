"""Payments (the `payments` table) — money in from factories or out to
baparis. Partial payments and FIFO bill-matching are handled in the
Phase 2 business logic; this table just records each payment.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from timber.db.engine import Base

# Direction of money flow.
PAYMENT_IN = "in"    # money arrived
PAYMENT_OUT = "out"  # money left


def natural_direction(party_type: str) -> str:
    """The direction money normally flows for this kind of party.

    We buy from baparis, so we pay them (out); we sell to factories, so they
    pay us (in). The reverse is legal but exceptional — a supplier refunding
    for rejected wood, or us refunding a factory.
    """
    from timber.db.models.party import PARTY_BAPARI

    return PAYMENT_OUT if party_type == PARTY_BAPARI else PAYMENT_IN


def settles_debt(party_type: str, direction: str) -> bool:
    """True if this payment reduces what is outstanding for the party.

    A payment in the natural direction settles; one against it adds to the
    balance, exactly like a fresh load would.
    """
    return direction == natural_direction(party_type)

# Methods.
METHOD_CASH = "cash"
METHOD_ONLINE = "online"
METHOD_BANK = "bank"
METHOD_CHEQUE = "cheque"

# Cheque lifecycle.
CHEQUE_PENDING = "pending"
CHEQUE_CLEARED = "cleared"
CHEQUE_BOUNCED = "bounced"


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The date the payment is EFFECTIVE / was received — drives the ledger and
    # which week it settles. The operator sets this (may be back-dated).
    txn_date: Mapped[date] = mapped_column(Date)
    # The date the record was actually typed in (audit only; defaults to the
    # day of entry). Lets "received in week 2, entered in week 3" land in
    # week 2 while still recording when it was booked. NULL on legacy rows.
    entry_date: Mapped[date | None] = mapped_column(Date, default=None)

    party_id: Mapped[int] = mapped_column(ForeignKey("parties.id"))

    direction: Mapped[str]  # "in" | "out"
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    method: Mapped[str] = mapped_column(default=METHOD_CASH)
    bank_name: Mapped[str | None]
    reference_no: Mapped[str | None]  # cheque no / online txn id

    notes: Mapped[str | None]
    is_void: Mapped[bool] = mapped_column(default=False)

    # For cheque payments: pending until it clears. A pending/cleared cheque
    # settles the party right away, but only a CLEARED cheque moves the bank
    # balance. A bounced cheque reverses (excluded everywhere). NULL for
    # non-cheque payments.
    cheque_status: Mapped[str | None] = mapped_column(default=None)
    cleared_date: Mapped[date | None] = mapped_column(Date, default=None)

    # Factory split sub-ledger side this payment settles: "left" (the weekly
    # side) or "right" (the irregular side). NULL = left/unspecified. Only
    # meaningful for factory payments when the factory has a split_rate.
    split_side: Mapped[str | None] = mapped_column(default=None)

    # Which business bank account the money moved through (None = cash
    # not tied to an account). Drives that account's running balance.
    bank_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_accounts.id")
    )

    # Which of the PARTY's own accounts the money went to / came from.
    party_bank_id: Mapped[int | None] = mapped_column(
        ForeignKey("party_banks.id")
    )

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    party: Mapped["Party"] = relationship()
    bank_account: Mapped["BankAccount | None"] = relationship()
    party_bank: Mapped["PartyBank | None"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} dir={self.direction!r} "
            f"amount={self.amount} method={self.method!r}>"
        )
