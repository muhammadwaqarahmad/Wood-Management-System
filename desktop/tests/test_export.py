"""Tests for report building and PDF/Excel export."""

from datetime import date
from decimal import Decimal

import pytest

from timber.core import excel_export, pdf_export
from timber.core.report_data import daily_book_report, party_statement, profit_loss
from timber.core.payment_service import create_payment
from timber.core.transaction_service import create_bapari_txn
from timber.db.models import Party
from timber.db.models.party import PARTY_BAPARI


@pytest.fixture
def bapari(session):
    p = Party(name="Karim", party_type=PARTY_BAPARI)
    session.add(p)
    session.flush()
    create_bapari_txn(
        session, txn_date=date(2026, 1, 1), party_id=p.id, weight=10, rate=1000
    )
    create_payment(session, txn_date=date(2026, 1, 2), party_id=p.id, amount=4000)
    return p


def test_party_statement_shape(session, bapari):
    report = party_statement(session, bapari.id)
    assert len(report.headers) == 5
    assert len(report.rows) == 2  # one load + one payment
    assert report.summary[0][1] == "6,000.00"


def test_profit_loss_rows(session, bapari):
    report = profit_loss(session)
    labels = [r[0] for r in report.rows]
    assert any("payable" in label.lower() or label for label in labels)
    assert len(report.rows) == 6


def test_pdf_written(session, bapari, tmp_path):
    report = party_statement(session, bapari.id)
    out = tmp_path / "statement.pdf"
    pdf_export.write(report, out)
    assert out.exists() and out.stat().st_size > 0
    assert out.read_bytes().startswith(b"%PDF")


def test_excel_written(session, bapari, tmp_path):
    report = party_statement(session, bapari.id)
    out = tmp_path / "statement.xlsx"
    excel_export.write(report, out)
    assert out.exists() and out.stat().st_size > 0


def test_bank_balances_report(session, tmp_path):
    from timber.core import bank_service
    from timber.core.report_data import bank_balances_report

    bank_service.create_account(
        session, created_by=None, name="Meezan", bank_name="Meezan",
        account_number="111", branch="Hyd", opening_balance=50000)
    bank_service.create_account(
        session, created_by=None, name="HBL", bank_name="HBL",
        opening_balance=25000)
    session.flush()

    report = bank_balances_report(session)
    assert report.headers[-1] == "Available balance"
    by_name = {r[0]: r for r in report.rows}
    assert by_name["Meezan"][-1] == "50,000.00"
    assert by_name["HBL"][-1] == "25,000.00"
    # Total available across active accounts is the summary line.
    total = dict(report.summary)["Total available"]
    assert total == "75,000.00"
    # Exports to both formats.
    pdf_export.write(report, tmp_path / "banks.pdf")
    excel_export.write(report, tmp_path / "banks.xlsx")
    assert (tmp_path / "banks.pdf").exists()
    assert (tmp_path / "banks.xlsx").exists()


def test_all_bank_books_report(session, tmp_path):
    """Bank Accounts export = each account's bank book (a section per account)."""
    from timber.core import bank_service
    from timber.core.payment_service import create_payment
    from timber.core.report_data import all_bank_books_report

    acc = bank_service.create_account(
        session, created_by=None, name="Meezan", opening_balance=1000)
    p = Party(name="Star", party_type="factory")
    session.add(p)
    session.flush()
    create_payment(
        session, txn_date=date(2026, 8, 1), party_id=p.id, amount=500,
        method="online", bank_account_id=acc.id)

    report = all_bank_books_report(session)
    # The account with a movement shows up as its own bank-book section.
    assert any("Meezan" in s.title for s in report.sections)
    meezan = next(s for s in report.sections if "Meezan" in s.title)
    assert meezan.headers[0] == "Date" and meezan.rows
    pdf_export.write(report, tmp_path / "bankbooks.pdf")
    assert (tmp_path / "bankbooks.pdf").exists()


def test_reports_combined_report(session):
    """Reports selectable export: single = native, both parties = 2-column list."""
    from timber.core import admin_service
    from timber.core.report_data import reports_combined_report
    from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY

    admin_service.create_party(session, name="Fac1", party_type=PARTY_FACTORY)
    admin_service.create_party(session, name="Sup1", party_type=PARTY_BAPARI)
    session.flush()

    # One section -> native report (has its own headers table, no sections).
    one = reports_combined_report(session, {"factory"})
    assert one.headers and not one.sections

    # Factories + suppliers -> two DESKTOP-format tables (not a merged 2-col list).
    both = reports_combined_report(session, {"factory", "supplier"})
    assert len(both.sections) == 2

    # All -> cash-flow sections + party tables, with a hero total.
    allsel = reports_combined_report(session, {"cashflow", "factory", "supplier"})
    assert allsel.sections and allsel.hero is not None


def test_financial_position_recv_give_two_column(session, bapari):
    """Financial Position's Receivable | Giveable export is a single two-column
    section, and BOTH sides are populated. Regression: PositionParty.kind is
    'supplier', not 'bapari' — the old lookup silently dropped every supplier,
    which emptied the whole 'To give' side (all payables are suppliers).
    ``bapari`` (Karim) owes us nothing; we owe HIM 6,000, so he must appear on
    the payable (right-hand) side."""
    from timber.core.report_data import financial_position_report

    rep = financial_position_report(session, {"receivable", "payable"})
    assert len(rep.sections) == 1
    sec = rep.sections[0]
    assert len(sec.headers) == 6                 # name/mobile/amount x2
    assert sec.divider_after == 2                # middle divider line
    # The give (right) side is columns 3-5. The supplier must be there — this
    # is exactly what the "bapari" vs "supplier" bug dropped.
    give_names = [row[3] for row in sec.rows]
    assert "Karim" in give_names


def test_daily_book_report(session, bapari, tmp_path):
    report = daily_book_report(session, date(2026, 1, 1))
    # Daily book is now a chronological timeline: "Time" is the first column,
    # so the entry kind moved to index 1.
    assert report.headers[0] == "Time"
    assert any(r[1] == "Purchase" for r in report.rows)
    pdf_export.write(report, tmp_path / "day.pdf")
    assert (tmp_path / "day.pdf").exists()
