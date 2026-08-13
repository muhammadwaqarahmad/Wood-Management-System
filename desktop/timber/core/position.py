"""Financial position — the firm-wide "where do we stand" summary.

Three parts, mirroring the client's hand sheets:
  * Daily bank balance: every account's balance, plus Bank / Cash / Cheque
    subtotals and a grand total.
  * To receive (jama): everyone who owes us (a factory that owes, or a
    supplier we've over-paid) with contact + amount (positive).
  * To give (banam): everyone we owe (a supplier we owe, or a loan/lender)
    with contact + amount (negative).

Sign rule is the app-wide one: money we will RECEIVE is positive, money we
must GIVE is negative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from timber.core.bank_service import AccountBalance, all_balances
from timber.core.calculations import money
from timber.core.ledger import party_balance
from timber.core.loan_service import list_loans
from timber.core.payment_service import cheque_balance
from timber.db.models import Party
from timber.db.models.party import PARTY_BAPARI

ZERO = Decimal("0.00")


@dataclass
class PositionParty:
    name: str
    contact: str          # phone numbers (or lender note) joined
    kind: str             # "supplier" | "factory" | "loan"
    amount: Decimal       # display-signed: receivable +ve, payable -ve


@dataclass
class FinancialPosition:
    accounts: list[AccountBalance] = field(default_factory=list)
    bank_total: Decimal = ZERO       # all accounts except Cash
    cash_balance: Decimal = ZERO     # the Cash account
    cheque_total: Decimal = ZERO     # pending cheques (memo, not in grand total)
    unclaimed_total: Decimal = ZERO  # unattributed receipts sitting in the bank
    grand_total: Decimal = ZERO      # bank + cash
    receivables: list[PositionParty] = field(default_factory=list)
    payables: list[PositionParty] = field(default_factory=list)
    total_receivable: Decimal = ZERO
    total_payable: Decimal = ZERO    # negative


def _contact(party: Party) -> str:
    return ", ".join(ph.phone for ph in party.phones if ph.phone)


def financial_position(session: Session) -> FinancialPosition:
    pos = FinancialPosition()

    # --- banks -------------------------------------------------------
    pos.accounts = all_balances(session)
    cash = ZERO
    bank = ZERO
    for a in pos.accounts:
        if a.is_cash:
            cash += a.closing
        else:
            bank += a.closing
    pos.cash_balance = money(cash)
    pos.bank_total = money(bank)
    pos.cheque_total = cheque_balance(session)
    # Unattributed receipts already sit inside the account balances above;
    # surface the total so the grand total is explained (memo, not added).
    from timber.core.unknown_payment_service import total_unknown

    pos.unclaimed_total = total_unknown(session)
    pos.grand_total = money(pos.bank_total + pos.cash_balance)

    # --- parties (receivable / payable) ------------------------------
    from timber.core.ledger import all_party_balances

    balances = all_party_balances(session)  # every party in a few queries
    parties = session.scalars(
        select(Party)
        # _contact() reads party.phones for every row; without this each one
        # was its own query (57 extra round trips on the live data).
        .options(selectinload(Party.phones))
        .where(Party.is_active.is_(True)).order_by(Party.name)
    ).all()
    for p in parties:
        internal = balances.get(p.id, ZERO)
        is_supplier = p.party_type == PARTY_BAPARI
        # display: supplier = -(internal), factory = +(internal)
        amount = money(-internal if is_supplier else internal)
        if amount == ZERO:
            continue
        row = PositionParty(
            name=p.name, contact=_contact(p),
            kind="supplier" if is_supplier else "factory",
            amount=amount,
        )
        if amount > 0:
            pos.receivables.append(row)
        else:
            pos.payables.append(row)

    # --- loans: taken = we owe the lender (payable); given = the
    # borrower owes us (receivable) --------------------------------------
    from timber.db.models.loan import LOAN_GIVEN

    for loan in list_loans(session):
        if loan.outstanding <= 0:
            continue
        if loan.direction == LOAN_GIVEN:
            pos.receivables.append(PositionParty(
                name=loan.lender_name,
                contact=loan.account_name or "",
                kind="loan",
                amount=money(loan.outstanding),
            ))
        else:
            pos.payables.append(PositionParty(
                name=loan.lender_name,
                contact=loan.account_name or "",
                kind="loan",
                amount=money(-loan.outstanding),
            ))

    # Biggest first on each side.
    pos.receivables.sort(key=lambda r: r.amount, reverse=True)
    pos.payables.sort(key=lambda r: r.amount)  # most negative first
    pos.total_receivable = money(sum((r.amount for r in pos.receivables), ZERO))
    pos.total_payable = money(sum((r.amount for r in pos.payables), ZERO))
    return pos
