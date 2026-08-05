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


def test_daily_book_report(session, bapari, tmp_path):
    report = daily_book_report(session, date(2026, 1, 1))
    assert any(r[0] == "Purchase" for r in report.rows)
    pdf_export.write(report, tmp_path / "day.pdf")
    assert (tmp_path / "day.pdf").exists()
