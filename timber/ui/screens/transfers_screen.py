"""Account transfers — move money between accounts (cash -> bank, etc.).

Create from the top form; edit or delete existing transfers from the list.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
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
from timber.core import bank_service
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.db.engine import SessionLocal
from timber.db.models import BankAccount
from timber.ui.screens.table_utils import (
    SearchBox,
    attach_words,
    fill_table,
    fmt,
    make_table,
    words_label,
)


class TransferDialog(design.Dialog):
    """Create or edit a transfer. ``transfer=None`` means a new one."""

    def __init__(self, accounts, transfer=None, parent=None) -> None:
        super().__init__(i18n.tr("edit") if transfer else i18n.tr("transfer_money"),
                         "transfer", parent=parent, width=500)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(
            QDate(transfer.txn_date.year, transfer.txn_date.month, transfer.txn_date.day)
            if transfer else QDate.currentDate())
        self.field(i18n.tr("date"), self.date_edit)

        self.from_combo = QComboBox()
        self.to_combo = QComboBox()
        for acc_id, acc_name in accounts:
            self.from_combo.addItem(acc_name, acc_id)
            self.to_combo.addItem(acc_name, acc_id)
        if transfer is not None:
            fi = self.from_combo.findData(transfer.from_account_id)
            ti = self.to_combo.findData(transfer.to_account_id)
            if fi >= 0:
                self.from_combo.setCurrentIndex(fi)
            if ti >= 0:
                self.to_combo.setCurrentIndex(ti)
        elif self.to_combo.count() > 1:
            # A new transfer starts on two DIFFERENT accounts; defaulting both
            # to the first one only produced "source and destination must be
            # different" the moment you pressed Save.
            self.to_combo.setCurrentIndex(1)
        self.field(i18n.tr("from_account"), self.from_combo)
        self.field(i18n.tr("to_account"), self.to_combo)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setDecimals(2)
        self.amount_spin.setMaximum(1_000_000_000.0)
        self.amount_spin.setGroupSeparatorShown(True)
        if transfer is not None:
            self.amount_spin.setValue(float(transfer.amount))
        self.field(i18n.tr("amount"), self.amount_spin)

        self.note_edit = QLineEdit((transfer.note or "") if transfer else "")
        self.field(i18n.tr("notes"), self.note_edit)

        ok, _cancel = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    def values(self) -> dict:
        return dict(
            txn_date=self.date_edit.date().toPython(),
            from_account_id=self.from_combo.currentData(),
            to_account_id=self.to_combo.currentData(),
            amount=self.amount_spin.value(),
            note=self.note_edit.text().strip(),
        )


class TransfersScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        can = has_permission(current_user.role, Permission.MANAGE_PAYMENTS)

        root = QVBoxLayout(self)
        # Side inset so tiles / history card sit off the panel's rounded edge,
        # consistent with the other pages.
        root.setContentsMargins(22, 8, 22, 14)
        root.setSpacing(16)

        # The transfer form now opens as a DIALOG from a button — the same
        # pattern the Loans page uses — instead of occupying the top third of
        # the page permanently. The history gets that space.
        self.add_btn = QPushButton(i18n.tr("transfer_money"))
        self.add_btn.setStyleSheet(design.btn("primary"))
        self.add_btn.setIcon(icons.icon("transfer", "#ffffff", 15))
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setEnabled(can)
        self.add_btn.clicked.connect(self._add)

        # Totals across the loaded transfers.
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        t_cnt, self.tile_count = design.stat_tile(
            i18n.tr("transfers"), design.c("accent"), "transfer")
        t_amt, self.tile_total = design.stat_tile(
            i18n.tr("amount"), design.TONES["emerald"], "wallet")
        for t in (t_cnt, t_amt):
            tiles.addWidget(t, 1)
        tiles.addStretch(2)
        root.addLayout(tiles)

        self.table = make_table(
            [i18n.tr("date"), i18n.tr("from_account"), i18n.tr("to_account"),
             i18n.tr("amount"), i18n.tr("notes")]
        )
        self.search = SearchBox(self.table)
        # The history had no stretch priority, so the entry form above kept
        # squeezing it down to a couple of visible rows. Give it its own
        # titled card that takes all the leftover height.
        history = design.Card(i18n.tr("transfers"), "history")
        hrow = QHBoxLayout()
        hrow.setSpacing(9)
        # Period filter beside the search, matching the other money pages.
        self.period_combo = QComboBox()
        for key in ("day", "week", "month", "year", "all"):
            self.period_combo.addItem(i18n.tr(key), key)
        self.period_combo.setCurrentIndex(self.period_combo.findData("day"))
        self.period_combo.currentIndexChanged.connect(self.refresh)
        hrow.addWidget(QLabel(f"{i18n.tr('period')}:"))
        hrow.addWidget(self.period_combo)
        hrow.addWidget(self.search, 1)
        history.addL(hrow)
        self.table.setMinimumHeight(300)
        history.add(self.table)
        history.box.setStretch(history.box.count() - 1, 1)

        btns = QHBoxLayout()
        btns.addWidget(self.add_btn)   # primary "Transfer money" stays prominent
        # Edit / delete of existing transfers live in a Manage dropdown.
        self.manage_btn = design.manage_button([
            (i18n.tr("edit"), self._edit, "pencil"),
            None,
            (i18n.tr("delete"), self._delete, "trash", "danger"),
        ], parent=self)
        self.manage_btn.setEnabled(can)
        btns.addWidget(self.manage_btn)
        btns.addStretch()
        history.add(design.toolbar_wrap(btns))
        root.addWidget(history, 1)

        self.refresh()

    def _accounts(self):
        with SessionLocal() as session:
            return [
                (a.id, a.name) for a in session.scalars(
                    select(BankAccount).where(BankAccount.is_active.is_(True)).order_by(BankAccount.name)
                )
            ]

    def _range(self):
        """(start, end) for the selected period; (None, None) means all."""
        import calendar
        from datetime import date as _date, timedelta as _td

        period = self.period_combo.currentData()
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

    def refresh(self) -> None:
        start, end = self._range()
        with SessionLocal() as session:
            transfers = bank_service.list_transfers(session, start=start, end=end)
        self._ids = [t.id for t in transfers]
        fill_table(
            self.table,
            [[str(t.txn_date), t.from_name, t.to_name, fmt(t.amount), t.note] for t in transfers],
        )
        self.search.apply()
        self.tile_count.setText(str(len(transfers)))
        self.tile_total.setText(fmt(sum((t.amount for t in transfers), Decimal("0"))))

    def _add(self) -> None:
        """Open the transfer dialog and record what it returns."""
        dlg = TransferDialog(self._accounts(), None, self)
        if not dlg.exec():
            return
        v = dlg.values()
        try:
            with SessionLocal() as session:
                bank_service.create_transfer(
                    session, created_by=self.current_user.id, **v)
                # Strict rule: a transfer can't overdraw the source account.
                bank_service.ensure_not_overdrawn(session, v["from_account_id"])
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        self.refresh()

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("edit"), i18n.tr("select_item"))
            return None
        return self._ids[row]

    def _edit(self) -> None:
        tid = self._selected_id()
        if tid is None:
            return
        from timber.db.models import AccountTransfer
        with SessionLocal() as session:
            transfer = session.get(AccountTransfer, tid)
            dialog = TransferDialog(self._accounts(), transfer, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with SessionLocal() as session:
                v = dialog.values()
                bank_service.update_transfer(
                    session, tid, created_by=self.current_user.id, **v
                )
                # Guard the SOURCE account — editing the amount up (or moving
                # the transfer onto a different account) must not overdraw it.
                bank_service.ensure_not_overdrawn(session, v.get("from_account_id"))
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _delete(self) -> None:
        tid = self._selected_id()
        if tid is None:
            return
        if not design.confirm(self, i18n.tr("delete"), i18n.tr("confirm_delete"), danger=True):
            return
        try:
            with SessionLocal() as session:
                bank_service.delete_transfer(session, tid, created_by=self.current_user.id)
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()
