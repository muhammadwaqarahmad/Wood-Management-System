"""Tests for the calculation engine (the formulas)."""

from decimal import Decimal

from timber.core.calculations import (
    compute_bill,
    compute_net_amount,
    compute_profit,
    money,
)


def test_compute_bill():
    # 12.5 tons × 1,000 = 12,500.00
    assert compute_bill(Decimal("12.5"), Decimal("1000")) == Decimal("12500.00")


def test_compute_net_amount():
    # bill + freight + loading
    assert compute_net_amount(10000, 1500, 500) == Decimal("12000.00")


def test_compute_net_amount_defaults():
    assert compute_net_amount(10000) == Decimal("10000.00")


def test_compute_profit():
    # (1200 − 1000) × 15 = 3,000
    assert compute_profit(1200, 1000, 15) == Decimal("3000.00")


def test_compute_profit_can_be_negative():
    # Sold below cost -> loss
    assert compute_profit(900, 1000, 10) == Decimal("-1000.00")


def test_money_rounds_half_up():
    assert money(Decimal("1.005")) == Decimal("1.01")


def test_decimal_no_float_drift():
    # 0.1 + 0.2 must be exactly 0.30, not 0.30000000000000004
    assert compute_net_amount("0.1", "0.2", 0) == Decimal("0.30")
