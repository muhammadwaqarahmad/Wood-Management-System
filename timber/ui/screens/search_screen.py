"""Global search screen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.ui import design, icons
from timber.core.current_user import CurrentUser
from timber.core.search import global_search
from timber.db.engine import SessionLocal
from timber.ui.screens.table_utils import fill_table, make_table

_KIND_KEYS = {
    "party": "party",
    "purchase": "purchase",
    "sale": "sale",
    "payment": "payment",
}
# One accent per result kind, so the Type column reads at a glance.
_KIND_TONE = {
    "party": "indigo", "purchase": "emerald", "sale": "sky", "payment": "amber",
}


class SearchScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        design.refresh()
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # --- search bar ---
        top = QHBoxLayout()
        top.setSpacing(9)
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText(i18n.tr("search_hint"))
        self.query_edit.setStyleSheet(design.input_style())
        self.query_edit.setMinimumHeight(38)
        try:
            self.query_edit.addAction(
                icons.icon("search", design.c("muted"), 16),
                QLineEdit.ActionPosition.LeadingPosition)
        except Exception:  # noqa: BLE001 - decoration only
            pass
        self.query_edit.returnPressed.connect(self._search)

        # Advanced filters, on the same row as the search box.
        self.kind_filter = QComboBox()
        self.kind_filter.addItem(i18n.tr("all"), None)
        for key in ("party", "purchase", "sale", "payment"):
            self.kind_filter.addItem(i18n.tr(_KIND_KEYS.get(key, key)), key)
        self.kind_filter.setStyleSheet(design.input_style())
        self.kind_filter.setMinimumHeight(38)
        self.kind_filter.currentIndexChanged.connect(self._search)

        self.period_filter = QComboBox()
        for key in ("all", "day", "week", "month", "year"):
            self.period_filter.addItem(i18n.tr(key), key)
        self.period_filter.setStyleSheet(design.input_style())
        self.period_filter.setMinimumHeight(38)
        self.period_filter.currentIndexChanged.connect(self._search)

        self.search_btn = QPushButton(i18n.tr("search"))
        self.search_btn.setStyleSheet(design.btn("primary"))
        self.search_btn.setIcon(icons.icon("search", "#ffffff", 15))
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.clicked.connect(self._search)
        top.addWidget(self.query_edit, 1)
        top.addWidget(QLabel(i18n.tr("type")))
        top.addWidget(self.kind_filter)
        top.addWidget(QLabel(i18n.tr("period")))
        top.addWidget(self.period_filter)
        top.addWidget(self.search_btn)
        root.addWidget(design.toolbar_wrap(top))

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(
            f"color:{design.c('muted')};font-size:12px;font-weight:600;padding-left:4px;")
        root.addWidget(self.count_label)

        self.table = make_table(
            [
                i18n.tr("type"),
                i18n.tr("date"),
                i18n.tr("name"),
                i18n.tr("detail"),
                i18n.tr("amount"),
            ]
        )
        root.addWidget(self.table, 1)

    def refresh(self) -> None:
        self.query_edit.setFocus()

    def _range(self):
        """(start, end) for the chosen period; (None, None) means any date."""
        import calendar
        from datetime import date as _date, timedelta as _td

        period = self.period_filter.currentData()
        today = _date.today()
        if period == "day":
            return today, today
        if period == "week":
            start = today - _td(days=today.weekday())
            return start, start + _td(days=6)
        if period == "month":
            last = calendar.monthrange(today.year, today.month)[1]
            return today.replace(day=1), today.replace(day=last)
        if period == "year":
            return _date(today.year, 1, 1), _date(today.year, 12, 31)
        return None, None

    def _search(self) -> None:
        query = self.query_edit.text().strip()
        kind = self.kind_filter.currentData()
        start, end = self._range()
        with SessionLocal() as session:
            results = global_search(
                session, query,
                kinds={kind} if kind else None, start=start, end=end,
            )
        fill_table(
            self.table,
            [
                [i18n.tr(_KIND_KEYS.get(r.kind, r.kind)), r.date, r.name, r.detail, r.amount]
                for r in results
            ],
            autosize=True,
        )
        # Tint the Type cell by kind so results scan quickly.
        from timber.ui.screens.table_utils import colour_cell
        for i, r in enumerate(results):
            tone = design.TONES.get(_KIND_TONE.get(r.kind, "slate"), "#64748b")
            colour_cell(self.table, i, 0, tone)
        self.count_label.setText(
            f"{i18n.tr('results')}: {len(results)}" if results else i18n.tr("no_results")
        )
