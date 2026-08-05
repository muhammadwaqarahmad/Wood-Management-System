"""Factory Sub-Ledger — the client's two-sided split ledger.

Each load's factory rate splits into a LEFT (weekly) side — remaining
rate × weight minus the factory-paid freight — and a RIGHT (irregular)
side — the factory's ``split_rate`` × weight, like the client's Excel
sheet with its two blocks and a pink divider.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.report_data import ReportData
from timber.core.split_ledger import factory_split_statement
from timber.db.engine import SessionLocal
from timber.db.models import Party
from timber.db.models.party import PARTY_FACTORY
from timber.ui.screens.export_helpers import export_buttons
from timber.ui.screens.table_utils import autosize_rows, fmt, make_table

_DIVIDER = QColor("#0f172a")  # bold dark line between the left and right sides


def _sum_card(title: str, c1: str, c2: str = "") -> tuple[QWidget, QLabel]:
    """A KPI tile: caption over a large value.

    Was a saturated gradient block with white text — the last page still
    drawing its own cards. Now the shared tile, so this ledger matches the
    Dashboard. ``c1`` becomes the accent bar; ``c2`` is ignored.
    """
    return design.stat_tile(title, c1)


class FactorySplitLedgerScreen(QWidget):
    """The split (two-sided) sub-ledger for factories with a split rate."""

    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        self._statement = None

        root = QVBoxLayout(self)

        # -- controls: factory, split rate, period ----------------------
        bar = QHBoxLayout()
        bar.setSpacing(8)
        # Add factory sits FIRST: with no factories enrolled the picker beside
        # it is empty, so the enrol action is what you actually need here.
        self.add_factory_btn = QPushButton("+ " + i18n.tr("add_split_factory"))
        self.add_factory_btn.setStyleSheet(design.btn("primary"))
        self.add_factory_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_factory_btn.clicked.connect(self._add_factory)
        bar.addWidget(self.add_factory_btn)

        bar.addWidget(QLabel(i18n.tr("factory")))
        # Only factories ENROLLED in the split ledger appear here (not every
        # factory uses two sides). Enrolling is a deliberate one-time action.
        # Type-to-filter picker, matching Buy & Sell and the other ledgers.
        from timber.ui.searchable import SearchableComboBox

        self.factory_combo = SearchableComboBox(i18n.tr("search"))
        self.factory_combo.setMinimumWidth(200)
        self.factory_combo.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.factory_combo)

        bar.addWidget(QLabel(i18n.tr("split_rate")))
        self.rate_spin = QDoubleSpinBox()
        self.rate_spin.setDecimals(2)
        self.rate_spin.setMaximum(1_000_000.0)
        self.rate_spin.setGroupSeparatorShown(True)
        bar.addWidget(self.rate_spin)
        # The rate itself stays editable (Save) — only the factory selection
        # is one-time.
        self.save_rate_btn = QPushButton(i18n.tr("save"))
        self.save_rate_btn.clicked.connect(self._save_rate)
        bar.addWidget(self.save_rate_btn)

        self.remove_factory_btn = QPushButton(i18n.tr("remove_split_factory"))
        self.remove_factory_btn.setStyleSheet(design.btn("danger"))
        self.remove_factory_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_factory_btn.clicked.connect(self._remove_factory)
        bar.addWidget(self.remove_factory_btn)

        bar.addWidget(QLabel(i18n.tr("period")))
        self.period_combo = QComboBox()
        for key in ("day", "month", "all", "custom"):
            self.period_combo.addItem(i18n.tr(key), key)
        self.period_combo.setCurrentIndex(self.period_combo.findData("day"))
        self.period_combo.currentIndexChanged.connect(self._period_changed)
        bar.addWidget(self.period_combo)
        today = QDate.currentDate()
        self.from_edit = QDateEdit()
        self.from_edit.setCalendarPopup(True)
        self.from_edit.setDisplayFormat("yyyy-MM-dd")
        self.from_edit.setDate(today.addMonths(-1))
        self.from_edit.dateChanged.connect(self.refresh)
        self.from_edit.setVisible(False)
        self.to_edit = QDateEdit()
        self.to_edit.setCalendarPopup(True)
        self.to_edit.setDisplayFormat("yyyy-MM-dd")
        self.to_edit.setDate(today)
        self.to_edit.dateChanged.connect(self.refresh)
        self.to_edit.setVisible(False)
        bar.addWidget(self.from_edit)
        bar.addWidget(self.to_edit)
        bar.addStretch()
        root.addWidget(design.toolbar_wrap(bar))

        # -- balance cards ----------------------------------------------
        cards = QHBoxLayout()
        cards.setSpacing(10)
        left_box, self.left_val = _sum_card(i18n.tr("left_balance"), "#2563eb", "#1e40af")
        right_box, self.right_val = _sum_card(i18n.tr("right_balance"), "#7c3aed", "#5b21b6")
        total_box, self.total_val = _sum_card(i18n.tr("combined_balance"), "#0d9488", "#0f766e")
        cards.addWidget(left_box, 1)
        cards.addWidget(right_box, 1)
        cards.addWidget(total_box, 1)
        root.addLayout(cards)

        self.hint = QLabel(i18n.tr("no_split_rate_hint"))
        self.hint.setStyleSheet("color: #d97706; font-weight: 600;")
        self.hint.setVisible(False)
        root.addWidget(self.hint)

        # -- the two-sided table ------------------------------------------
        # Shared columns, the LEFT (weekly) block (payment shows its route
        # under the amount, then a narrow wrapping Reference column), a thin
        # bold divider, and the RIGHT (regular) block.
        self._ref_col = 10
        self._div_col = 12
        headers = [
            i18n.tr("date"), i18n.tr("vehicle"), i18n.tr("wood"),
            # left (weekly) block
            i18n.tr("rate"), i18n.tr("weight"), "Kg",
            i18n.tr("total"), i18n.tr("freight"), i18n.tr("sale"),
            i18n.tr("payment"), i18n.tr("reference"), i18n.tr("balance"),
            "",  # hairline divider
            # right (regular) block
            i18n.tr("rate"), i18n.tr("weight"), "Kg",
            i18n.tr("total"), i18n.tr("payment"), i18n.tr("balance"),
        ]
        self.table = make_table(headers)
        self.table.setWordWrap(True)
        hdr = self.table.horizontalHeader()
        # Everything fits on one page: wide money columns stretch to share
        # the space, narrow fact columns get small fixed widths, long text
        # (payment routes, references) wraps onto extra lines instead.
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setMinimumSectionSize(5)   # let the divider be a thin dark line
        fixed = {
            0: 76,                 # date
            1: 62,                 # vehicle
            3: 52, 13: 52,         # rates
            4: 64, 14: 64,         # weights ("Weight" header must fit)
            5: 48, 15: 48,         # kg
            self._ref_col: 84,     # reference (wraps)
            self._div_col: 6,      # divider (bold dark line)
        }
        for col, width in fixed.items():
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, width)
        root.addWidget(self.table)

        root.addLayout(export_buttons(self, self._build_report, "factory_sub_ledger"))

        self.refresh_factories()

    # -- data -----------------------------------------------------------
    def _period_changed(self) -> None:
        custom = self.period_combo.currentData() == "custom"
        self.from_edit.setVisible(custom)
        self.to_edit.setVisible(custom)
        self.refresh()

    def _range(self) -> tuple[date | None, date | None]:
        code = self.period_combo.currentData()
        today = date.today()
        if code == "day":
            return today, today
        if code == "month":
            return today.replace(day=1), today
        if code == "custom":
            return self.from_edit.date().toPython(), self.to_edit.date().toPython()
        return None, None

    def refresh_factories(self, select_id: int | None = None) -> None:
        current = select_id if select_id is not None else self.factory_combo.currentData()
        with SessionLocal() as session:
            # Enrolled = added to the split ledger (split_rate is set, even if
            # still 0 pending the rate).
            factories = [
                (p.id, p.name)
                for p in session.scalars(
                    select(Party).where(
                        Party.party_type == PARTY_FACTORY,
                        Party.is_active.is_(True),
                        Party.split_rate.is_not(None),
                    ).order_by(Party.name)
                )
            ]
        self.factory_combo.blockSignals(True)
        self.factory_combo.clear()
        for pid, name in factories:
            self.factory_combo.addItem(name, pid)
        if current is not None:
            idx = self.factory_combo.findData(current)
            if idx >= 0:
                self.factory_combo.setCurrentIndex(idx)
        self.factory_combo.blockSignals(False)
        # Nothing enrolled yet -> guide the user to add a factory.
        empty = self.factory_combo.count() == 0
        self.hint.setText(
            i18n.tr("no_split_factory_hint") if empty else i18n.tr("no_split_rate_hint")
        )
        self.rate_spin.setEnabled(not empty)
        self.save_rate_btn.setEnabled(not empty)
        self.refresh()

    def _add_factory(self) -> None:
        """One-time enrollment: pick a factory not yet in the split ledger.
        The split rate is set afterwards from the main bar."""
        from PySide6.QtWidgets import QComboBox as _Combo, QDialog

        with SessionLocal() as session:
            available = [
                (p.id, p.name)
                for p in session.scalars(
                    select(Party).where(
                        Party.party_type == PARTY_FACTORY,
                        Party.is_active.is_(True),
                        Party.split_rate.is_(None),
                    ).order_by(Party.name)
                )
            ]
        if not available:
            info_toast(
                self, i18n.tr("add_split_factory"), i18n.tr("all_factories_enrolled")
            )
            return

        dlg = design.Dialog(i18n.tr("add_split_factory"), "factory",
                            parent=self, width=460)
        combo = _Combo()
        for pid, name in available:
            combo.addItem(name, pid)
        dlg.field(i18n.tr("factory"), combo)
        ok, _cancel = dlg.buttons(i18n.tr("save"))
        ok.clicked.connect(dlg.accept)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        pid = combo.currentData()
        with SessionLocal() as session:
            party = session.get(Party, pid)
            party.split_rate = 0  # enrolled; rate set from the main bar
            session.commit()
            info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        self.refresh_factories(select_id=pid)

    def _save_rate(self) -> None:
        pid = self.factory_combo.currentData()
        if not pid:
            return
        with SessionLocal() as session:
            party = session.get(Party, pid)
            # Enrolment is split_rate IS NOT NULL; 0 means "enrolled, no rate
            # set yet". The old ``value() or None`` turned a saved rate of 0
            # back into NULL, silently dropping the factory OUT of the split
            # ledger. Enrolment now ends only via "Remove from split ledger".
            party.split_rate = Decimal(str(self.rate_spin.value()))
            session.commit()
            info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        self.refresh()

    def _remove_factory(self) -> None:
        """The ONLY way out of the split ledger — deliberate and confirmed."""
        pid = self.factory_combo.currentData()
        if not pid:
            info_toast(self, i18n.tr("remove"), i18n.tr("select_item"))
            return
        name = self.factory_combo.currentText()
        if not design.confirm(self, i18n.tr("remove_split_factory"),
                              i18n.tr("remove_split_confirm").replace("{name}", name),
                              danger=True):
            return
        with SessionLocal() as session:
            party = session.get(Party, pid)
            party.split_rate = None          # un-enrolled
            session.commit()
        info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        self.refresh_factories()

    def refresh(self) -> None:
        pid = self.factory_combo.currentData()
        if not pid:
            self.table.setRowCount(0)
            self._statement = None
            for v in (self.left_val, self.right_val, self.total_val):
                v.setText("—")
            self.hint.setVisible(True)  # "add a factory to the split ledger"
            return
        start, end = self._range()
        with SessionLocal() as session:
            st = factory_split_statement(session, pid, start, end)
        self._statement = st
        self.rate_spin.setValue(float(st.split_rate))
        self.hint.setVisible(st.split_rate <= 0)

        self.left_val.setText(fmt(st.closing_left))
        self.right_val.setText(fmt(st.closing_right))
        self.total_val.setText(fmt(st.closing_total))

        def _pay_cell(amount, route: str) -> str:
            """Payment amount with its route (bank → bank / Cash) below."""
            if not amount:
                return ""
            return f"{fmt(amount)}\n{route}" if route else fmt(amount)

        self.table.setRowCount(len(st.entries))
        for r, e in enumerate(st.entries):
            if e.kind == "load":
                values = [
                    str(e.txn_date), e.vehicle, e.wood,
                    fmt(e.left_rate), f"{e.weight:,.2f}", f"{e.kg:,.0f}",
                    fmt(e.left_total),
                    fmt(e.freight) if e.freight else "",
                    fmt(e.left_net), "", "", fmt(e.left_balance),
                    "",
                    fmt(e.right_rate), f"{e.weight:,.2f}", f"{e.kg:,.0f}",
                    fmt(e.right_amount), "", fmt(e.right_balance),
                ]
            else:
                values = [
                    str(e.txn_date), "", "",
                    "", "", "", "", "", "",
                    _pay_cell(e.left_payment, e.detail),
                    e.ref, fmt(e.left_balance),
                    "",
                    "", "", "", "",
                    _pay_cell(e.right_payment, e.detail),
                    fmt(e.right_balance),
                ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c >= 3 and c not in (self._ref_col, self._div_col):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if c == self._div_col:
                    item.setBackground(_DIVIDER)
                self.table.setItem(r, c, item)
        # This table builds its items by hand, so it uses the standalone
        # sizer rather than fill_table's inline pass.
        autosize_rows(self.table)

    # -- export -----------------------------------------------------------
    def _build_report(self) -> ReportData:
        st = self._statement
        if st is None:
            raise ValueError("Nothing to export.")
        headers = [
            i18n.tr("date"), i18n.tr("vehicle"), i18n.tr("wood"),
            f"{i18n.tr('weekly_side')} — {i18n.tr('rate')}",
            i18n.tr("weight"), "Kg",
            i18n.tr("total"), i18n.tr("freight"), i18n.tr("sale"),
            i18n.tr("payment"), i18n.tr("reference"), i18n.tr("balance"),
            f"{i18n.tr('irregular_side')} — {i18n.tr('rate')}",
            i18n.tr("weight"), "Kg", i18n.tr("total"),
            i18n.tr("payment"), i18n.tr("balance"),
        ]

        def _pay(amount, route: str) -> str:
            if not amount:
                return ""
            return f"{fmt(amount)} {route}".strip() if route else fmt(amount)

        rows = []
        for e in st.entries:
            if e.kind == "load":
                rows.append([
                    str(e.txn_date), e.vehicle, e.wood,
                    fmt(e.left_rate), f"{e.weight:,.2f}", f"{e.kg:,.0f}",
                    fmt(e.left_total),
                    fmt(e.freight) if e.freight else "",
                    fmt(e.left_net), "", "", fmt(e.left_balance),
                    fmt(e.right_rate), f"{e.weight:,.2f}", f"{e.kg:,.0f}",
                    fmt(e.right_amount), "", fmt(e.right_balance),
                ])
            else:
                rows.append([
                    str(e.txn_date), "", "",
                    "", "", "", "", "", "",
                    _pay(e.left_payment, e.detail), e.ref,
                    fmt(e.left_balance),
                    "", "", "", "",
                    _pay(e.right_payment, e.detail),
                    fmt(e.right_balance),
                ])
        return ReportData(
            title=f"{i18n.tr('factory_sub_ledger')} — {st.factory_name}",
            headers=headers,
            rows=rows,
            divider_after=11,  # bold line between the left (weekly) & right sides
            summary=[
                (i18n.tr("left_balance"), fmt(st.closing_left)),
                (i18n.tr("right_balance"), fmt(st.closing_right)),
                (i18n.tr("combined_balance"), fmt(st.closing_total)),
            ],
        )
