"""The calculation engine — every formula from the plan, as pure
functions. No database, no UI: just numbers in, numbers out, which
makes them easy to test and reuse everywhere.

All money is rounded to 2 decimal places with banker-safe HALF_UP
rounding; everything is ``Decimal`` to avoid float errors on rupees.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

TWO_PLACES = Decimal("0.01")
KG_PER_MAUND = Decimal("40")


def sale_weight(muds, kg=0) -> Decimal:
    """Billable weight on a SALE = maunds + kg/40 (kg counts)."""
    return to_decimal(muds) + (to_decimal(kg or 0) / KG_PER_MAUND)

# What a single load contributes to a party's running balance.
# Per the plan: bill + freight (loading is tracked in net_amount but
# does NOT move the balance). Centralised here so the rule is one edit.
#   -> change this function if freight/loading treatment differs.


def to_decimal(value: Any) -> Decimal:
    """Coerce ints/floats/strings/Decimals to Decimal safely."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value: Any) -> Decimal:
    """Round a value to 2 decimal places (rupees.paise)."""
    return to_decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def compute_bill(weight: Any, rate: Any) -> Decimal:
    """Bill / بل = weight × rate."""
    return money(to_decimal(weight) * to_decimal(rate))


def compute_net_amount(bill: Any, freight: Any = 0, loading: Any = 0) -> Decimal:
    """Net amount = bill + freight + loading."""
    return money(to_decimal(bill) + to_decimal(freight) + to_decimal(loading))


def compute_profit(factory_rate: Any, bapari_rate: Any, weight: Any) -> Decimal:
    """Profit per load = (factory rate − bapari rate) × weight."""
    return money((to_decimal(factory_rate) - to_decimal(bapari_rate)) * to_decimal(weight))


def balance_amount(bill: Any, freight: Any = 0) -> Decimal:
    """How much a load adds to a party's balance (bill + freight)."""
    return money(to_decimal(bill) + to_decimal(freight))


def apply_txn_totals(txn: Any) -> None:
    """Fill ``bill`` and ``net_amount`` on a BapariTxn/FactoryTxn in place.

    Works on either model via duck typing (both have weight, rate,
    freight, loading). Call this before saving a transaction. Blank
    (None) freight/loading are normalised to 0.00 first.
    """
    txn.freight = money(txn.freight or 0)
    txn.loading = money(txn.loading or 0)
    txn.bill = compute_bill(txn.weight, txn.rate)
    txn.net_amount = compute_net_amount(txn.bill, txn.freight, txn.loading)
