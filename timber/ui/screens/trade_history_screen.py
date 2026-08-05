"""Trades — every buy & sell record, with search and an advanced date
filter (all / day / week / month / year / custom range).
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design, icons
from timber.core.current_user import CurrentUser
from timber.core.labels import expenses_summary
from timber.core.permissions import Permission, has_permission
from timber.core.report_data import ReportData, trades_report
from timber.core.reports import count_trades, list_trades, trades_totals
from timber.core.transaction_service import update_mixed_trade, void_trade
from timber.db.engine import SessionLocal
from timber.db.models import CombinedTxn, Party, WoodType
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.ui.screens.export_helpers import export_buttons
from timber.ui.screens.trade_entry import ExpenseInput, WoodLinesWidget
from timber.ui.screens.table_utils import (
    SearchBox,
    fill_table,
    fmt,
    make_table,
)
from PySide6.QtWidgets import QHeaderView


class TradeEditDialog(design.Dialog):
    """Edit a saved trade — single or mixed-load (Manager/Admin only)."""

    def __init__(self, group_id: int, parent=None) -> None:
        # The wood line was narrowed (see trade_entry width constants), so the
        # dialog no longer has to be enormous to show the supplier half.
        super().__init__(i18n.tr("edit"), "history", parent=parent, width=900)
        # If the screen is too narrow for that, scroll sideways rather than
        # silently clipping the supplier columns.
        self._body_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        from timber.core.transaction_service import _group_members

        root = self.body
        form = QFormLayout()

        with SessionLocal() as session:
            anchor = session.get(CombinedTxn, group_id)
            members = sorted(_group_members(session, anchor), key=lambda c: c.id)
            first = members[0]
            b0, f0 = first.bapari_txn, first.factory_txn
            baparis = [
                (p.id, p.name) for p in session.scalars(
                    select(Party).where(Party.party_type == PARTY_BAPARI).order_by(Party.name)
                )
            ]
            factories = [
                (p.id, p.name) for p in session.scalars(
                    select(Party).where(Party.party_type == PARTY_FACTORY).order_by(Party.name)
                )
            ]
            woods = [(w.id, w.name) for w in session.scalars(select(WoodType).order_by(WoodType.name))]
            d = b0.txn_date
            line_data = [
                (c.bapari_txn.wood_type_id, float(c.bapari_txn.muds), float(c.bapari_txn.kg),
                 float(c.bapari_txn.rate), float(c.factory_txn.rate),
                 float(c.factory_txn.muds), float(c.factory_txn.kg))
                for c in members
            ]
            cur = dict(
                vehicle=b0.vehicle_no or "",
                bapari_id=b0.party_id, factory_id=f0.party_id,
                loading=float(first.loading_amount), loading_payer=first.loading_payer,
                loading_payer2=first.loading_payer2, loading_split=float(first.loading_split),
                freight=float(first.freight_amount), freight_payer=first.freight_payer,
                freight_payer2=first.freight_payer2, freight_split=float(first.freight_split),
                unloading=float(first.unloading_amount), unloading_payer=first.unloading_payer,
                unloading_payer2=first.unloading_payer2, unloading_split=float(first.unloading_split),
            )

        # Two fields per row: stacked, these four rows alone made the dialog
        # taller than most laptop screens.
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def _cell(row, col, label, widget):
            box = QVBoxLayout()
            box.setSpacing(5)
            cap = QLabel(label.upper())
            cap.setStyleSheet(
                f"color:{design.c('muted')};font-size:11px;font-weight:700;"
                "letter-spacing:0.6px;")
            widget.setMinimumHeight(36)
            box.addWidget(cap)
            box.addWidget(widget)
            grid.addLayout(box, row, col)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate(d.year, d.month, d.day))
        self.vehicle_edit = QLineEdit(cur["vehicle"])
        self.bapari_combo = self._combo(baparis, cur["bapari_id"])
        self.factory_combo = self._combo(factories, cur["factory_id"])

        _cell(0, 0, i18n.tr("date"), self.date_edit)
        _cell(0, 1, i18n.tr("vehicle_no"), self.vehicle_edit)
        _cell(1, 0, i18n.tr("bapari"), self.bapari_combo)
        _cell(1, 1, i18n.tr("factory"), self.factory_combo)
        root.addLayout(grid)

        self.lines_widget = WoodLinesWidget(woods)
        for wood_id, muds, kg, br, fr, f_muds, f_kg in line_data:
            self.lines_widget.add_row(wood_id, muds, kg, br, fr, f_muds, f_kg)
        root.addWidget(self.lines_widget)

        exp_form = QFormLayout()
        self.loading_exp = ExpenseInput()
        self.loading_exp.set_values(cur["loading"], cur["loading_payer"],
                                    cur["loading_payer2"], cur["loading_split"])
        exp_form.addRow(i18n.tr("loading"), self.loading_exp)
        self.freight_exp = ExpenseInput()
        self.freight_exp.set_values(cur["freight"], cur["freight_payer"],
                                    cur["freight_payer2"], cur["freight_split"])
        exp_form.addRow(i18n.tr("freight"), self.freight_exp)
        self.unloading_exp = ExpenseInput()
        self.unloading_exp.set_values(cur["unloading"], cur["unloading_payer"],
                                      cur["unloading_payer2"], cur["unloading_split"])
        exp_form.addRow(i18n.tr("unloading"), self.unloading_exp)
        root.addLayout(exp_form)

        ok, _cancel = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    @staticmethod
    def _combo(items, current, optional=False) -> QComboBox:
        from timber.ui.searchable import SearchableComboBox

        combo = SearchableComboBox(i18n.tr("search"))
        if optional:
            combo.addItem("—", None)
        for item_id, name in items:
            combo.addItem(name, item_id)
        idx = combo.findData(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
            combo.lineEdit().setText(combo.itemText(idx))
        return combo

    def values(self) -> dict:
        return dict(
            txn_date=self.date_edit.date().toPython(),
            bapari_id=self.bapari_combo.currentData(),
            factory_id=self.factory_combo.currentData(),
            lines=self.lines_widget.lines(),
            vehicle_no=self.vehicle_edit.text().strip(),
            loading_amount=self.loading_exp.amount(),
            loading_payer=self.loading_exp.payer(),
            loading_payer2=self.loading_exp.payer2(),
            loading_split=self.loading_exp.split(),
            freight_amount=self.freight_exp.amount(),
            freight_payer=self.freight_exp.payer(),
            freight_payer2=self.freight_exp.payer2(),
            freight_split=self.freight_exp.split(),
            unloading_amount=self.unloading_exp.amount(),
            unloading_payer=self.unloading_exp.payer(),
            unloading_payer2=self.unloading_exp.payer2(),
            unloading_split=self.unloading_exp.split(),
        )


class TradeHistoryScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        self._ids: list[int] = []
        root = QVBoxLayout(self)


        # --- filter row ---
        filters = QHBoxLayout()
        filters.addWidget(QLabel(f"{i18n.tr('period')}:"))
        self.period_combo = QComboBox()
        for key in ("all", "day", "week", "month", "year", "custom"):
            self.period_combo.addItem(i18n.tr(key), key)
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        filters.addWidget(self.period_combo)

        filters.addWidget(QLabel(i18n.tr("date_from")))
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("yyyy-MM-dd")
        self.from_date.setDate(QDate.currentDate())
        self.from_date.dateChanged.connect(self.refresh)
        filters.addWidget(self.from_date)

        filters.addWidget(QLabel(i18n.tr("date_to")))
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setDate(QDate.currentDate())
        self.to_date.dateChanged.connect(self.refresh)
        filters.addWidget(self.to_date)
        # Row cap. Rendering every trade ever recorded took ~2.5s at 3,000
        # trades and grows linearly, so the page shows the most recent N by
        # default. The count label always states the true total, and exports
        # always cover the whole range regardless of this setting.
        filters.addWidget(QLabel(f"{i18n.tr('show')}:"))
        self.limit_combo = QComboBox()
        for label, value in (("200", 200), ("500", 500), ("1000", 1000),
                             (i18n.tr("all"), 0)):
            self.limit_combo.addItem(label, value)
        self.limit_combo.setCurrentIndex(0)          # 200 — snappy default open
        self.limit_combo.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.limit_combo)

        filters.addStretch()
        root.addWidget(design.toolbar_wrap(filters))

        # --- KPI tiles (period totals; filled in refresh) ---
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        tile_count, self.tile_count = design.stat_tile(
            i18n.tr("trades"), design.c("accent"), "receipt")
        tile_weight, self.tile_weight = design.stat_tile(
            i18n.tr("total_weight"), design.TONES["slate"], "database")
        tile_sales, self.tile_sales = design.stat_tile(
            i18n.tr("total_sales"), design.TONES["sky"], "wallet")
        tile_profit, self.tile_profit = design.stat_tile(
            i18n.tr("total_profit"), design.TONES["emerald"], "trending-up")
        for t in (tile_count, tile_weight, tile_sales, tile_profit):
            tiles.addWidget(t, 1)
        root.addLayout(tiles)

        # --- action bar: search on the left, row actions + export on the right ---
        self.table = make_table(
            [
                i18n.tr("date"), i18n.tr("vehicle_no"), i18n.tr("wood_type"),
                i18n.tr("weight"), i18n.tr("bapari"), i18n.tr("buy_rate"),
                i18n.tr("factory"), i18n.tr("sell_rate"),
                i18n.tr("purchase_bill"), i18n.tr("sale_bill"),
                i18n.tr("freight"), i18n.tr("profit"),
            ]
        )
        # All columns share the full width (Stretch); the freight column is
        # pinned to a fixed, moderate width so long "amount (who paid)" text
        # wraps onto several lines instead of stretching across the screen.
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(10, QHeaderView.ResizeMode.Fixed)  # freight
        self.table.setColumnWidth(10, 185)
        self.table.setWordWrap(True)
        self.search = SearchBox(self.table)

        actions = design.Toolbar()
        actions.add(self.search)
        actions.spacer()
        can_edit = has_permission(current_user.role, Permission.EDIT_TRADE)
        self.edit_btn = QPushButton(i18n.tr("edit"))
        self.edit_btn.setStyleSheet(design.btn("ghost"))
        self.edit_btn.setIcon(icons.icon("pencil", design.c("text"), 15))
        self.edit_btn.clicked.connect(self._edit)
        self.edit_btn.setEnabled(can_edit)
        actions.add(self.edit_btn)
        self.delete_btn = QPushButton(i18n.tr("delete"))
        self.delete_btn.setStyleSheet(design.btn("danger"))
        self.delete_btn.setIcon(icons.icon("trash", "#ffffff", 15))
        self.delete_btn.clicked.connect(self._delete)
        self.delete_btn.setEnabled(can_edit)
        actions.add(self.delete_btn)
        for btn in export_buttons(self, self._build_report, "trades", as_widgets=True):
            actions.add(btn)
        root.addWidget(actions)

        root.addWidget(self.table, 1)

        # Opens on TODAY, matching the Dashboard and Reports. "All" is one
        # click away in the same dropdown.
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentIndex(self.period_combo.findData("day"))
        self.period_combo.blockSignals(False)
        self._on_period_changed()  # sets initial enabled state + loads

    def _edit(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("edit"), i18n.tr("select_item"))
            return
        dialog = TradeEditDialog(self._ids[row], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with SessionLocal() as session:
                update_mixed_trade(
                    session, self._ids[row], created_by=self.current_user.id,
                    **dialog.values(),
                )
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _delete(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("delete"), i18n.tr("select_item"))
            return
        if not design.confirm(self, i18n.tr("delete"), i18n.tr("confirm_delete"), danger=True):
            return
        try:
            with SessionLocal() as session:
                void_trade(session, self._ids[row], created_by=self.current_user.id)
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    # -- date range from the selected period -------------------------
    def _range(self) -> tuple[date | None, date | None]:
        period = self.period_combo.currentData()
        # Day/week/month/year are anchored on TODAY. The from-box is the custom
        # range's start only — anchoring on it would let a date left over from a
        # previous custom range silently shift "This month" into the past, and
        # the box is now hidden so nobody could see why.
        anchor = (self.from_date.date().toPython()
                  if period == "custom" else date.today())
        if period == "all":
            return None, None
        if period == "day":
            return anchor, anchor
        if period == "week":
            start = anchor - timedelta(days=anchor.weekday())
            return start, start + timedelta(days=6)
        if period == "month":
            last = calendar.monthrange(anchor.year, anchor.month)[1]
            return anchor.replace(day=1), anchor.replace(day=last)
        if period == "year":
            return date(anchor.year, 1, 1), date(anchor.year, 12, 31)
        # custom
        return anchor, self.to_date.date().toPython()

    def _on_period_changed(self) -> None:
        period = self.period_combo.currentData()
        # The date boxes belong to the CUSTOM range only. For Today / This
        # week / This month / This year the period speaks for itself, so the
        # boxes are hidden rather than sitting there greyed out.
        custom = period == "custom"
        self.from_date.setVisible(custom)
        self.to_date.setVisible(custom)
        self.from_date.setEnabled(custom)
        self.to_date.setEnabled(custom)
        self.refresh()

    def _build_report(self) -> ReportData:
        start, end = self._range()
        with SessionLocal() as session:
            return trades_report(session, start, end)

    def refresh(self) -> None:
        start, end = self._range()
        limit = self.limit_combo.currentData() or None
        with SessionLocal() as session:
            trades = list_trades(session, start, end, limit=limit)
            total = count_trades(session, start, end) if limit else len(trades)
            # Totals must cover the WHOLE range, not just the rows shown, or a
            # capped view would silently under-report the period's profit.
            total_profit, total_sales, total_muds = trades_totals(session, start, end)
        self._ids = [t.id for t in trades]
        fill_table(
            self.table,
            [
                [
                    str(t.txn_date), t.vehicle, t.wood, t.weight_text,
                    t.bapari_name,
                    "—" if t.is_mixed else fmt(t.bapari_rate),
                    t.factory_name,
                    "—" if t.is_mixed else fmt(t.factory_rate),
                    fmt(t.purchase_bill), fmt(t.sale_bill),
                    expenses_summary(t, sep="\n"), fmt(t.profit),
                ]
                for t in trades
            ],
            autosize=True
        )
        self.search.apply()
        shown = (f"{len(trades)} / {total}" if total > len(trades) else str(total))
        self.tile_count.setText(shown)
        self.tile_weight.setText(f"{total_muds:g} {i18n.tr('muds')}")
        self.tile_sales.setText(fmt(total_sales))
        self.tile_profit.setText(fmt(total_profit))
        # Profit tile turns red if the period is a net loss.
        self.tile_profit.setStyleSheet(
            f"color:{design.amt_color(total_profit)};font-size:21px;font-weight:800;")
