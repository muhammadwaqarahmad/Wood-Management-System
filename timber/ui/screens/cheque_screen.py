"""Cheques — pending cheques (issued/received) with their own balance.
A pending cheque settles the party now but only moves the bank balance
when it CLEARS. BOUNCE reverses it. Cheques are created on the Payment
page (method = Cheque); here you clear or bounce them."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design
from timber.core import payment_service
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.db.engine import SessionLocal
from timber.db.models.payment import (
    CHEQUE_BOUNCED,
    CHEQUE_CLEARED,
    CHEQUE_PENDING,
    PAYMENT_IN,
)
from timber.ui.screens.table_utils import (
    SearchBox,
    colour_cell,
    fill_table,
    fmt,
    make_table,
)

_STATUS_KEY = {CHEQUE_PENDING: "pending", CHEQUE_CLEARED: "cleared", CHEQUE_BOUNCED: "bounced"}
_STATUS_COLOUR = {CHEQUE_PENDING: "#b45309", CHEQUE_CLEARED: "#16a34a", CHEQUE_BOUNCED: "#c62828"}


class ChequeScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        can = has_permission(current_user.role, Permission.MANAGE_PAYMENTS)

        root = QVBoxLayout(self)

        # Cheque balance + a live status breakdown, as tiles.
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        t_bal, self.balance_label = design.stat_tile(
            i18n.tr("cheque_balance"), design.TONES["amber"], "file-check")
        t_pend, self.tile_pending = design.stat_tile(
            i18n.tr("pending"), design.TONES["sky"], "alarm-clock")
        t_clear, self.tile_cleared = design.stat_tile(
            i18n.tr("cleared"), design.TONES["emerald"], "check-circle")
        t_bounce, self.tile_bounced = design.stat_tile(
            i18n.tr("bounced"), design.TONES["rose"], "alert-triangle")
        for t in (t_bal, t_pend, t_clear, t_bounce):
            tiles.addWidget(t, 1)
        root.addLayout(tiles)

        bar = QHBoxLayout()
        bar.addStretch()
        bar.addWidget(QLabel(f"{i18n.tr('status')}:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem(i18n.tr("all"), None)
        self.status_filter.addItem(i18n.tr("pending"), CHEQUE_PENDING)
        self.status_filter.addItem(i18n.tr("cleared"), CHEQUE_CLEARED)
        self.status_filter.addItem(i18n.tr("bounced"), CHEQUE_BOUNCED)
        # Pending is the working list — those are the cheques still to clear.
        self.status_filter.setCurrentIndex(
            self.status_filter.findData(CHEQUE_PENDING))
        self.status_filter.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.status_filter)
        self._filter_bar = bar          # the search is inserted below
        root.addWidget(design.toolbar_wrap(bar))

        self.table = make_table([
            i18n.tr("date"), i18n.tr("party"), i18n.tr("direction"),
            i18n.tr("amount"), i18n.tr("bank_account"), i18n.tr("reference"),
            i18n.tr("status"), i18n.tr("cleared_date"),
        ])
        # Search sits WITH the status filter rather than on its own row.
        # Inserted at the FRONT (the bar opens with a stretch that pushes the
        # status filter right), so it reads: search ......... status.
        self.search = SearchBox(self.table)
        self._filter_bar.insertWidget(0, self.search, 1)
        root.addWidget(self.table)

        buttons = QHBoxLayout()
        self.clear_btn = QPushButton(i18n.tr("clear_cheque"))
        self.bounce_btn = QPushButton(i18n.tr("bounce_cheque"))
        self.clear_btn.clicked.connect(self._clear)
        self.bounce_btn.clicked.connect(self._bounce)
        self.bounce_btn.setStyleSheet(design.btn("danger"))
        for b in (self.clear_btn, self.bounce_btn):
            b.setEnabled(can)
            buttons.addWidget(b)
        buttons.addStretch()
        root.addWidget(design.toolbar_wrap(buttons))

        self.refresh()

    def refresh(self) -> None:
        status = self.status_filter.currentData()
        with SessionLocal() as session:
            rows = payment_service.list_cheques(session, status=status)
            bal = payment_service.cheque_balance(session)
        self._ids = [r.id for r in rows]
        self._statuses = [r.status for r in rows]
        fill_table(self.table, [
            [
                str(r.txn_date), r.party_name,
                i18n.tr("received_in") if r.direction == PAYMENT_IN else i18n.tr("issued"),
                fmt(r.amount), r.account_name, r.reference,
                i18n.tr(_STATUS_KEY.get(r.status, "pending")),
                str(r.cleared_date) if r.cleared_date else "",
            ]
            for r in rows
        ])
        for i, r in enumerate(rows):
            colour_cell(self.table, i, 6, _STATUS_COLOUR.get(r.status, "#475569"))
        self.search.apply()
        self.balance_label.setText(fmt(bal))
        # Counts reflect the rows currently loaded (respects the status filter).
        counts = {}
        for r in rows:
            counts[r.status] = counts.get(r.status, 0) + 1
        self.tile_pending.setText(str(counts.get(CHEQUE_PENDING, 0)))
        self.tile_cleared.setText(str(counts.get(CHEQUE_CLEARED, 0)))
        self.tile_bounced.setText(str(counts.get(CHEQUE_BOUNCED, 0)))

    def _selected(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("cheques"), i18n.tr("select_item"))
            return None
        if self._statuses[row] != CHEQUE_PENDING:
            info_toast(self, i18n.tr("cheques"), i18n.tr("select_item"))
            return None
        return self._ids[row]

    def _clear(self) -> None:
        cid = self._selected()
        if cid is None:
            return
        with SessionLocal() as session:
            payment_service.clear_cheque(session, cid, created_by=self.current_user.id)
            session.commit()
            info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        self.refresh()

    def _bounce(self) -> None:
        cid = self._selected()
        if cid is None:
            return
        if not design.confirm(self, i18n.tr("bounce_cheque"), i18n.tr("confirm_delete"), danger=True):
            return
        with SessionLocal() as session:
            payment_service.bounce_cheque(session, cid, created_by=self.current_user.id)
            session.commit()
            info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        self.refresh()
