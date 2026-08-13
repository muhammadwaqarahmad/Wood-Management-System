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
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
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
from timber.core.split_ledger import (
    factory_split_statement,
    set_split_rates,
    split_rate_map,
    traded_wood_types,
)
from timber.core.weekly_settlement import week_label
from timber.db.engine import SessionLocal
from timber.db.models import Party
from timber.db.models.party import PARTY_FACTORY
from timber.ui.screens.export_helpers import export_buttons
from timber.ui.screens.table_utils import autosize_rows, fmt, make_table


def _date_cell(e, sep: str = "\n") -> str:
    """Date shown for a sub-ledger row. Payments show the received date and,
    the entry (booking) date beneath it. Applies to both trades and payments —
    the actual date on top, the entry date below (always shown so both dates
    are visible; they match when a row was entered on its own date)."""
    if e.booked_date:
        return f"{e.txn_date}{sep}{i18n.tr('entry_date')}: {e.booked_date}"
    return str(e.txn_date)


def _weekly_status(bal) -> str:
    """Weekly-side settlement state for a row: 'Settled' when the weekly
    balance is clear, else the amount still pending — which rolls into the
    next week (shown with a → arrow)."""
    if bal == 0:
        return i18n.tr("settled")
    if bal > 0:
        return f"{fmt(bal)} →"   # pending — carries to the next week
    return fmt(bal)              # advance / overpaid


_DIVIDER = QColor("#0f172a")  # bold dark line between the left and right sides


def _sum_card(title: str, c1: str, icon: str = "") -> tuple[QWidget, QLabel]:
    """A KPI tile: caption over a large value.

    Was a saturated gradient block with white text — the last page still
    drawing its own cards. Now the shared tile, so this ledger matches the
    Dashboard. ``c1`` becomes the accent bar; ``icon`` is the gradient chip.
    """
    return design.stat_tile(title, c1, icon)


class _SplitRatesDialog(design.Dialog):
    """Per-wood split rates for one factory: one editable amount per wood
    type it has traded. 0 means no split (whole rate stays weekly)."""

    def __init__(self, factory_name, woods, current, parent=None) -> None:
        super().__init__(i18n.tr("set_split_rates"), "factory",
                         subtitle=factory_name, parent=parent, width=460)
        self._spins: dict[int, QDoubleSpinBox] = {}

        hint = QLabel(i18n.tr("split_rate_for_wood"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{design.c('muted')};font-size:11px;")
        self.body.addWidget(hint)

        if not woods:
            msg = QLabel(i18n.tr("no_traded_woods"))
            msg.setWordWrap(True)
            self.body.addWidget(msg)
            ok, _cancel = self.buttons(i18n.tr("save"))
            ok.setEnabled(False)  # nothing to save yet
            return

        # Compact two-column form: wood name on the left, its rate on the right
        # (reads far better than a tall stack of captioned inputs).
        from PySide6.QtWidgets import QFormLayout, QWidget
        host = QWidget()
        form = QFormLayout(host)
        form.setContentsMargins(0, 8, 0, 2)
        form.setSpacing(9)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        for wid, wname in woods:
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setMaximum(1_000_000.0)
            spin.setGroupSeparatorShown(True)
            spin.setValue(float(current.get(wid, 0)))
            spin.setMinimumWidth(160)
            lbl = QLabel(wname)
            lbl.setStyleSheet(f"font-weight:600;color:{design.c('text')};")
            form.addRow(lbl, spin)
            self._spins[wid] = spin
        self.body.addWidget(host)

        ok, _cancel = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    def values(self) -> dict:
        return {
            wid: Decimal(str(sp.value())) for wid, sp in self._spins.items()
        }


class FactorySplitLedgerScreen(QWidget):
    """The split (two-sided) sub-ledger for factories with a split rate."""

    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        self._statement = None

        root = QVBoxLayout(self)
        # Side inset so controls / cards / table sit off the panel's rounded
        # edge, consistent with the other pages.
        root.setContentsMargins(22, 8, 22, 14)
        root.setSpacing(12)

        # -- controls: factory picker, a compact "Manage" menu, period ---
        # The bar stays clean: just the factory search and the period. Every
        # factory action (add / set split rates / remove) tucks into one
        # "Manage" dropdown, and each action opens its own dialog.
        bar = QHBoxLayout()
        bar.setSpacing(10)

        bar.addWidget(QLabel(i18n.tr("factory")))
        from timber.ui.searchable import SearchableComboBox

        self.factory_combo = SearchableComboBox(i18n.tr("search"))
        self.factory_combo.setMinimumWidth(240)
        self.factory_combo.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.factory_combo)

        self.manage_btn = design.manage_button([
            (i18n.tr("add_split_factory"), self._add_factory, "plus"),
            (i18n.tr("set_split_rates"), self._set_rates, "pencil"),
            None,
            (i18n.tr("remove_split_factory"), self._remove_factory, "trash", "danger"),
        ], parent=self)  # added on the far right below

        bar.addSpacing(18)
        self.period_label = QLabel(i18n.tr("period"))
        bar.addWidget(self.period_label)
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
        bar.addWidget(self.manage_btn)  # Manage sits on the far right
        root.addWidget(design.toolbar_wrap(bar))

        # -- balance cards (detailed mode) ------------------------------
        self.detail_cards = QWidget()
        cards = QHBoxLayout(self.detail_cards)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(10)
        left_box, self.left_val = _sum_card(i18n.tr("left_balance"), "#2563eb", "calendar-clock")
        right_box, self.right_val = _sum_card(i18n.tr("right_balance"), "#7c3aed", "wallet")
        total_box, self.total_val = _sum_card(i18n.tr("combined_balance"), "#0d9488", "pie-chart")
        cards.addWidget(left_box, 1)
        cards.addWidget(right_box, 1)
        cards.addWidget(total_box, 1)
        root.addWidget(self.detail_cards)

        self.hint = QLabel(i18n.tr("no_split_rate_hint"))
        self.hint.setStyleSheet("color: #d97706; font-weight: 600;")
        self.hint.setVisible(False)
        root.addWidget(self.hint)

        # -- the two-sided table ------------------------------------------
        # A "Week" column after the date, the LEFT (weekly) block ending in a
        # "Weekly status" column (Settled / amount pending → next week), a thin
        # bold divider, then the RIGHT (regular) block. Payments show only their
        # amount; there is no Reference column.
        self._status_col = 12
        self._div_col = 13
        headers = [
            i18n.tr("date"), i18n.tr("week"), i18n.tr("vehicle"), i18n.tr("wood"),
            # left (weekly) block
            i18n.tr("rate"), i18n.tr("weight"), "Kg",
            i18n.tr("total"), i18n.tr("freight"), i18n.tr("sale"),
            i18n.tr("payment"), i18n.tr("balance"), i18n.tr("weekly_status"),
            "",  # hairline divider
            # right (regular) block
            i18n.tr("rate"), i18n.tr("weight"), "Kg",
            i18n.tr("total"), i18n.tr("payment"), i18n.tr("balance"),
        ]
        self.table = make_table(headers)
        self.table.setWordWrap(True)
        hdr = self.table.horizontalHeader()
        # Everything fits on one page: wide money columns stretch to share the
        # space, narrow fact columns get small fixed widths.
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setMinimumSectionSize(5)   # let the divider be a thin dark line
        fixed = {
            0: 132,                # date (fits the "Entry date: <date>" 2nd line)
            1: 58,                 # week (e.g. "15–21")
            2: 62,                 # vehicle
            4: 52, 14: 52,         # rates
            5: 64, 15: 64,         # weights ("Weight" header must fit)
            6: 48, 16: 48,         # kg
            self._status_col: 96,  # weekly status (Settled / amount →)
            self._div_col: 6,      # divider (bold dark line)
        }
        for col, width in fixed.items():
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, width)
        root.addWidget(self.table)
        # Detailed ledger export (also drives the top-right page toolbar).
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
        self.refresh()

    def _add_factory(self) -> None:
        """One-time enrollment: pick a factory not yet in the split ledger.
        The split rate is set afterwards from the main bar."""
        from PySide6.QtWidgets import QDialog

        from timber.ui.searchable import SearchableComboBox

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
        # Type-to-filter picker (matches the main factory picker) — easier when
        # there are many factories to choose from.
        combo = SearchableComboBox(i18n.tr("search"))
        for pid, name in available:
            combo.addItem(name, pid)
        combo.setCurrentIndex(-1)
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

    def _set_rates(self) -> None:
        """Open the per-wood split-rate editor for the selected factory."""
        pid = self.factory_combo.currentData()
        if not pid:
            info_toast(self, i18n.tr("set_split_rates"), i18n.tr("select_item"))
            return
        name = self.factory_combo.currentText()
        with SessionLocal() as session:
            woods = traded_wood_types(session, pid)
            current = split_rate_map(session, pid)
        dlg = _SplitRatesDialog(name, woods, current, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        with SessionLocal() as session:
            set_split_rates(session, pid, dlg.values())
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
        self._refresh_detailed(pid)

    def _refresh_detailed(self, pid: int) -> None:
        start, end = self._range()
        with SessionLocal() as session:
            st = factory_split_statement(session, pid, start, end)
            has_rates = bool(split_rate_map(session, pid))
        self._statement = st
        # Hint appears until at least one wood type has a split rate configured.
        self.hint.setVisible(not has_rates)

        self.left_val.setText(fmt(st.closing_left))
        self.right_val.setText(fmt(st.closing_right))
        self.total_val.setText(fmt(st.closing_total))

        def _pay_cell(amount) -> str:
            """Just the payment amount — no bank route/account shown."""
            return fmt(amount) if amount else ""

        # Settled / not-settled highlight colors for the weekly-status column.
        from timber.ui import theme as _theme
        _dark = _theme.get_theme() == "dark"
        _c_settled = "#34d399" if _dark else "#059669"   # green
        _c_pending = "#fb7185" if _dark else "#e11d48"   # red

        self.table.setRowCount(len(st.entries))
        for r, e in enumerate(st.entries):
            wk = week_label(e.txn_date)
            status = _weekly_status(e.left_balance)
            if e.kind == "load":
                values = [
                    _date_cell(e), wk, e.vehicle, e.wood,
                    fmt(e.left_rate), f"{e.weight:,.2f}", f"{e.kg:,.0f}",
                    fmt(e.left_total),
                    fmt(e.freight) if e.freight else "",
                    fmt(e.left_net), "", fmt(e.left_balance), status,
                    "",
                    fmt(e.right_rate), f"{e.weight:,.2f}", f"{e.kg:,.0f}",
                    fmt(e.right_amount), "", fmt(e.right_balance),
                ]
            else:
                values = [
                    _date_cell(e), wk, "", "",
                    "", "", "", "", "", "",
                    _pay_cell(e.left_payment), fmt(e.left_balance), status,
                    "",
                    "", "", "", "",
                    _pay_cell(e.right_payment),
                    fmt(e.right_balance),
                ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                # Cols 0-3 (date, week, vehicle, wood) read left; money right.
                # The weekly-status column is text, so keep it left too.
                if c >= 4 and c not in (self._div_col, self._status_col):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if c == self._div_col:
                    item.setBackground(_DIVIDER)
                # Highlight the weekly settlement status: green = settled,
                # red = still owing (that amount rolls to the next week).
                if c == self._status_col and value:
                    item.setForeground(QBrush(QColor(
                        _c_settled if e.left_balance == 0 else _c_pending)))
                self.table.setItem(r, c, item)
        # This table builds its items by hand, so it uses the standalone
        # sizer rather than fill_table's inline pass.
        autosize_rows(self.table)

    # -- export -----------------------------------------------------------
    def _build_report(self) -> ReportData:
        """The detailed two-sided ledger export (top-right toolbar)."""
        st = self._statement
        if st is None:
            raise ValueError("Nothing to export.")
        headers = [
            i18n.tr("date"), i18n.tr("week"), i18n.tr("vehicle"), i18n.tr("wood"),
            f"{i18n.tr('weekly_side')} — {i18n.tr('rate')}",
            i18n.tr("weight"), "Kg",
            i18n.tr("total"), i18n.tr("freight"), i18n.tr("sale"),
            i18n.tr("payment"), i18n.tr("balance"), i18n.tr("weekly_status"),
            f"{i18n.tr('irregular_side')} — {i18n.tr('rate')}",
            i18n.tr("weight"), "Kg", i18n.tr("total"),
            i18n.tr("payment"), i18n.tr("balance"),
        ]

        def _pay(amount) -> str:
            return fmt(amount) if amount else ""

        rows = []
        for e in st.entries:
            wk = week_label(e.txn_date)
            status = _weekly_status(e.left_balance)
            if e.kind == "load":
                rows.append([
                    _date_cell(e, " · "), wk, e.vehicle, e.wood,
                    fmt(e.left_rate), f"{e.weight:,.2f}", f"{e.kg:,.0f}",
                    fmt(e.left_total),
                    fmt(e.freight) if e.freight else "",
                    fmt(e.left_net), "", fmt(e.left_balance), status,
                    fmt(e.right_rate), f"{e.weight:,.2f}", f"{e.kg:,.0f}",
                    fmt(e.right_amount), "", fmt(e.right_balance),
                ])
            else:
                rows.append([
                    _date_cell(e, " · "), wk, "", "",
                    "", "", "", "", "", "",
                    _pay(e.left_payment), fmt(e.left_balance), status,
                    "", "", "", "",
                    _pay(e.right_payment),
                    fmt(e.right_balance),
                ])
        return ReportData(
            title=f"{i18n.tr('factory_sub_ledger')} — {st.factory_name}",
            headers=headers,
            rows=rows,
            divider_after=12,  # bold line between the left (weekly) & right sides
            summary=[
                (i18n.tr("left_balance"), fmt(st.closing_left)),
                (i18n.tr("right_balance"), fmt(st.closing_right)),
                (i18n.tr("combined_balance"), fmt(st.closing_total)),
            ],
        )
