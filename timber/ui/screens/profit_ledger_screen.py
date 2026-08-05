"""Profit ledger — every combined load with its margin, plus headline
totals for sales, purchases, profit and the overall margin %."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.report_data import ReportData, profit_ledger_report
from timber.core.reports import profit_ledger, profit_totals
from timber.db.engine import SessionLocal
from timber.ui.screens.export_helpers import export_buttons
from timber.ui.screens.table_utils import (
    SearchBox,
    card_strip,
    colour_cell,
    fill_table,
    fmt,
    make_table,
    stat_card,
)


class ProfitLedgerScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self._root = QVBoxLayout(self)


        self._cards = QWidget()
        self._root.addWidget(self._cards)

        self.table = make_table(
            [
                i18n.tr("date"),
                i18n.tr("bapari"),
                i18n.tr("factory"),
                i18n.tr("weight"),
                i18n.tr("buy_rate"),
                i18n.tr("sell_rate"),
                i18n.tr("profit"),
                i18n.tr("margin_pct"),
            ]
        )
        # Same unbounded-render cap as the other ledgers; the cards above
        # always summarise every trade regardless of this setting.
        cap = QHBoxLayout()
        cap.addWidget(QLabel(f"{i18n.tr('show')}:"))
        self.limit_combo = QComboBox()
        for lbl, val in (("200", 200), ("500", 500), ("1000", 1000), (i18n.tr("all"), 0)):
            self.limit_combo.addItem(lbl, val)
        self.limit_combo.setCurrentIndex(0)
        self.limit_combo.currentIndexChanged.connect(self.refresh)
        cap.addWidget(self.limit_combo)
        self.search = SearchBox(self.table)
        cap.addWidget(self.search, 1)
        self._root.addWidget(design.toolbar_wrap(cap))
        self._root.addWidget(self.table)
        self._root.addLayout(
            export_buttons(self, self._build_report, "profit_ledger")
        )
        self.refresh()

    def _build_report(self) -> ReportData:
        with SessionLocal() as session:
            return profit_ledger_report(session)

    def _rebuild_cards(self, totals) -> None:
        self._cards.deleteLater()
        self._cards = QWidget()
        layout = QVBoxLayout(self._cards)
        layout.setContentsMargins(0, 0, 0, 0)
        profit_colour = "#2e7d32" if totals.profit >= 0 else "#c62828"
        layout.addLayout(
            card_strip(
                [
                    stat_card(
                        i18n.tr("total_profit"), fmt(totals.profit), profit_colour,
                        f"{totals.trades} {i18n.tr('trades')}",
                    ),
                    stat_card(i18n.tr("total_sales"), fmt(totals.sale), "#1565c0"),
                    stat_card(
                        i18n.tr("total_purchases"), fmt(totals.purchase), "#6d28d9"
                    ),
                    stat_card(
                        i18n.tr("avg_margin"), f"{totals.margin_pct:g}%", "#00838f"
                    ),
                ]
            )
        )
        self._root.insertWidget(1, self._cards)

    def refresh(self) -> None:
        with SessionLocal() as session:
            rows, total = profit_ledger(session)
            totals = profit_totals(rows, total)

        self._rebuild_cards(totals)
        limit = self.limit_combo.currentData() or 0
        rows = rows[-limit:] if limit else rows   # newest N (rows are oldest-first)

        fill_table(
            self.table,
            [
                [
                    str(r.txn_date),
                    r.bapari_name,
                    r.factory_name,
                    f"{r.weight:g}",
                    fmt(r.bapari_rate),
                    fmt(r.factory_rate),
                    fmt(r.profit),
                    f"{r.margin_pct:g}%",
                ]
                for r in rows
            ],
        )
        for i, r in enumerate(rows):
            colour_cell(self.table, i, 6, "#2e7d32" if r.profit >= 0 else "#c62828")
        self.search.apply()
