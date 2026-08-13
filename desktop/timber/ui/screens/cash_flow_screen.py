"""Cash-flow forecast — cash now, receivables by due date, payables."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.reports import cash_flow_forecast
from timber.db.engine import SessionLocal
from timber.ui.screens.table_utils import fill_table, fmt, make_table


def _card(title: str, value: str, colour: str) -> QFrame:
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background:{colour}; border-radius:10px; }}"
        "QLabel { color: white; background: transparent; }"
    )
    box = QVBoxLayout(frame)
    box.setContentsMargins(12, 10, 12, 10)
    t = QLabel(title)
    t.setStyleSheet("font-size: 12px; color: rgba(255,255,255,0.9);")
    v = QLabel(value)
    v.setStyleSheet("font-size: 19px; font-weight: bold; color: white;")
    box.addWidget(t)
    box.addWidget(v)
    shadow = QGraphicsDropShadowEffect(frame)
    shadow.setBlurRadius(18)
    shadow.setColor(QColor(0, 0, 0, 55))
    shadow.setOffset(0, 3)
    frame.setGraphicsEffect(shadow)
    return frame


class CashFlowScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self._root = QVBoxLayout(self)
        header = QLabel(i18n.tr("cash_flow_forecast"))
        header.setStyleSheet(
            f"color:{design.c('text')};font-size:18px;font-weight:800;")
        self._root.addWidget(header)

        self._body = QWidget()
        self._root.addWidget(self._body)
        self.refresh()

    def refresh(self) -> None:
        with SessionLocal() as session:
            f = cash_flow_forecast(session)

        # rebuild body
        self._body.deleteLater()
        self._body = QWidget()
        layout = QVBoxLayout(self._body)

        grid = QGridLayout()
        cards = [
            (i18n.tr("current_cash"), fmt(f.current_cash), "#00838f"),
            (i18n.tr("total_receivable"), fmt(f.total_receivable), "#1565c0"),
            (i18n.tr("total_payable"), fmt(f.total_payable), "#c62828"),
            (i18n.tr("projected_cash"), fmt(f.projected), "#2e7d32"),
        ]
        for i, (t, v, c) in enumerate(cards):
            grid.addWidget(_card(t, v, c), 0, i)
        layout.addLayout(grid)

        layout.addWidget(QLabel(i18n.tr("expected_in")))
        table = make_table([i18n.tr("period"), i18n.tr("amount")])
        fill_table(
            table,
            [
                [i18n.tr("overdue_report"), fmt(f.overdue_in)],
                [i18n.tr("due_7"), fmt(f.due_7)],
                [i18n.tr("due_30"), fmt(f.due_30)],
                [i18n.tr("due_later"), fmt(f.later)],
            ],
        )
        layout.addWidget(table)
        self._root.addWidget(self._body)
