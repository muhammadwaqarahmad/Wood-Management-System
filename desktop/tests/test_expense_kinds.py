"""Business vs house expense buckets + filtered stats + dashboard summary."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import expense_service
from timber.core.dashboard_service import dashboard_summary


def _seed(session):
    expense_service.create_expense(
        session, txn_date=date(2026, 7, 1), category="rent", amount=1000,
        kind="business",
    )
    expense_service.create_expense(
        session, txn_date=date(2026, 7, 2), category="grocery", amount=400,
        kind="house",
    )
    expense_service.create_expense(
        session, txn_date=date(2026, 6, 1), category="fuel", amount=250,
    )  # default kind -> business


def test_kind_totals_and_stats(session):
    _seed(session)
    assert expense_service.total_expenses(session, kind="business") == Decimal("1250.00")
    assert expense_service.total_expenses(session, kind="house") == Decimal("400.00")

    st = expense_service.expense_stats(session)
    assert st.total == Decimal("1650.00")
    assert st.business == Decimal("1250.00")
    assert st.house == Decimal("400.00")
    assert st.count == 3
    assert st.by_category[0] == ("rent", Decimal("1000.00"))


def test_date_filter_and_list(session):
    _seed(session)
    july = expense_service.list_expenses(
        session, start=date(2026, 7, 1), end=date(2026, 7, 31)
    )
    assert [r.category for r in july] == ["rent", "grocery"]
    assert july[0].kind == "business" and july[1].kind == "house"

    only_house = expense_service.list_expenses(session, kind="house")
    assert len(only_house) == 1 and only_house[0].category == "grocery"


def test_bad_kind_rejected(session):
    with pytest.raises(ValueError):
        expense_service.create_expense(
            session, txn_date=date(2026, 7, 1), category="x", amount=10,
            kind="weird",
        )


def test_dashboard_summary_shape(session):
    _seed(session)
    d = dashboard_summary(session, date(2026, 7, 1), date(2026, 7, 31))
    assert d["cards"]["expBusiness"] == 1000.0   # only July business expense
    assert d["cards"]["expHouse"] == 400.0
    assert d["bucket"] == "day"
    # plus/minus table ends with the net position row
    assert d["table"][-1]["key"] == "net_worth"
    signs = {r["key"]: r["sign"] for r in d["table"]}
    assert signs["payable"] == -1 and signs["banks"] == 1
