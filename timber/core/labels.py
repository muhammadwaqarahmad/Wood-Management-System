"""Shared display helpers for expense payers (who paid loading / freight /
unloading) — used by both the report builders and the UI screens.

The payer resolves to a real name: 'us' -> the business name, 'bapari' ->
the trade's supplier name, 'factory' -> the trade's factory name.
"""

from __future__ import annotations

from decimal import Decimal

from timber import i18n
from timber.db.models.combined_txn import PAYER_BAPARI, PAYER_FACTORY, PAYER_US


def expenses_summary(row, supplier_name=None, factory_name=None, sep=" ; ") -> str:
    """Combine a trade's loading + freight + unloading into one cell, each
    line showing the amount and who paid, e.g.
    'Freight: 500 (Karim); Loading: 200 (Abdul Sattar Woods)'. Pass
    ``sep="\\n"`` for a multi-line cell."""
    sup = supplier_name if supplier_name is not None else getattr(row, "supplier_name", None) or getattr(row, "bapari_name", None)
    fac = factory_name if factory_name is not None else getattr(row, "factory_name", None)
    parts = []
    for amt, p1, p2, split, key in (
        (row.freight, row.freight_payer, row.freight_payer2, row.freight_split, "freight"),
        (row.loading, row.loading_payer, row.loading_payer2, row.loading_split, "loading"),
        (row.unloading, row.unloading_payer, row.unloading_payer2, row.unloading_split, "unloading"),
    ):
        text = expense_text(amt, p1, sup, fac, p2, split)
        if text:
            parts.append(f"{i18n.tr(key)}: {text}")
    return sep.join(parts)


def payment_route(payment, party_name: str | None = None) -> str:
    """Describe where a payment's money moved: from which of our accounts
    to the party (supplier), or from the party (factory) into our account.
    Falls back to 'Cash' when no business bank account is tied to it."""
    from timber.db.models.payment import METHOD_CASH, PAYMENT_OUT

    our = payment.bank_account.name if payment.bank_account else None
    if our is None:
        our = i18n.tr("cash") if payment.method == METHOD_CASH else (payment.bank_name or i18n.tr("cash"))
    other = None
    if payment.party_bank is not None:
        other = payment.party_bank.bank_name or payment.party_bank.account_title
    if not other:
        other = party_name or ""
    if payment.direction == PAYMENT_OUT:
        # We paid the supplier: money left our account → their account.
        return f"{our} → {other}".strip(" →") if other else our
    # Money came in from the factory → into our account.
    return f"{other} → {our}".strip(" →") if other else our


def payer_label(
    code: str, supplier_name: str | None = None, factory_name: str | None = None
) -> str:
    if code == PAYER_US:
        return i18n.tr("payer_us")               # business name
    if code == PAYER_BAPARI:
        return supplier_name or i18n.tr("bapari")
    if code == PAYER_FACTORY:
        return factory_name or i18n.tr("factory")
    return i18n.tr(code)


def expense_text(
    amount, payer: str,
    supplier_name: str | None = None, factory_name: str | None = None,
    payer2: str | None = None, split=0,
) -> str:
    """Format an expense with who paid it. Single payer -> '500.00 (Karim)';
    split -> '500.00 (350.00 Abdul Sattar Woods, 150.00 ABC)'. Empty if 0.
    ``split`` is the rupee amount the first payer bears."""
    try:
        amt = Decimal(str(amount or 0))
    except Exception:  # noqa: BLE001
        amt = Decimal("0")
    if amt <= 0:
        return ""
    name1 = payer_label(payer, supplier_name, factory_name)
    try:
        primary = Decimal(str(split if split is not None else 0))
    except Exception:  # noqa: BLE001
        primary = Decimal("0")
    if payer2 and 0 < primary < amt:
        name2 = payer_label(payer2, supplier_name, factory_name)
        rest = amt - primary
        return f"{amt:,.2f} ({primary:,.2f} {name1}, {rest:,.2f} {name2})"
    return f"{amt:,.2f} ({name1})"
