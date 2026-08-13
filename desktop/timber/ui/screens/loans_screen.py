"""Loans — money borrowed from family/friends to keep cash flowing, and
repayments made later. Borrowing adds cash to an account; repaying takes
it out. Outstanding = principal - repayments."""

from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
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
from timber.ui import design
from timber.core import loan_service
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.db.engine import SessionLocal
from timber.db.models import BankAccount
from timber.ui.screens.table_utils import (
    SearchBox,
    colour_cell,
    fill_table,
    fmt,
    make_table,
)


def _accounts():
    with SessionLocal() as session:
        return [
            (a.id, a.name) for a in session.scalars(
                select(BankAccount).where(BankAccount.is_active.is_(True)).order_by(BankAccount.name)
            )
        ]


def _account_combo(accounts) -> QComboBox:
    combo = QComboBox()
    for acc_id, acc_name in accounts:
        combo.addItem(acc_name, acc_id)
    return combo


def _amount_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(2)
    spin.setMaximum(1_000_000_000.0)
    spin.setGroupSeparatorShown(True)
    return spin


class LoanDialog(design.Dialog):
    """Record a loan — taken (we borrow) or given (we lend out)."""

    def __init__(self, accounts, parent=None) -> None:
        super().__init__(i18n.tr("loans"), "hand-coins", parent=parent, width=500)
        from timber.db.models.loan import LOAN_GIVEN, LOAN_TAKEN

        self.direction_combo = QComboBox()
        self.direction_combo.addItem(i18n.tr("loan_taken"), LOAN_TAKEN)
        self.direction_combo.addItem(i18n.tr("loan_given"), LOAN_GIVEN)
        self.field(i18n.tr("loan_direction"), self.direction_combo)

        self.date_edit = QDateEdit(); self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd"); self.date_edit.setDate(QDate.currentDate())
        self.field(i18n.tr("date"), self.date_edit)
        self.lender_edit = QLineEdit()
        self.field(i18n.tr("person_name"), self.lender_edit)
        self.amount_spin = _amount_spin()
        self.field(i18n.tr("amount"), self.amount_spin)
        self.account_combo = _account_combo(accounts)
        self.field(i18n.tr("bank_account"), self.account_combo)
        self.return_edit = QDateEdit(); self.return_edit.setCalendarPopup(True)
        self.return_edit.setDisplayFormat("yyyy-MM-dd")
        self.return_edit.setDate(QDate.currentDate().addMonths(3))
        self.field(i18n.tr("expected_return"), self.return_edit)
        self.note_edit = QLineEdit()
        self.field(i18n.tr("notes"), self.note_edit)

        ok, _cancel = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    def values(self) -> dict:
        return dict(
            txn_date=self.date_edit.date().toPython(),
            direction=self.direction_combo.currentData(),
            lender_name=self.lender_edit.text().strip(),
            amount=self.amount_spin.value(),
            bank_account_id=self.account_combo.currentData(),
            expected_return_date=self.return_edit.date().toPython(),
            notes=self.note_edit.text().strip(),
        )


class RepayDialog(design.Dialog):
    def __init__(self, accounts, outstanding, parent=None) -> None:
        super().__init__(i18n.tr("repay_loan"), "hand-coins", parent=parent, width=460)
        self.add(QLabel(f"{i18n.tr('outstanding')}: {fmt(outstanding)}"))
        self.date_edit = QDateEdit(); self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd"); self.date_edit.setDate(QDate.currentDate())
        self.field(i18n.tr("date"), self.date_edit)
        self.amount_spin = _amount_spin()
        self.amount_spin.setValue(float(outstanding))
        self.field(i18n.tr("amount"), self.amount_spin)
        self.account_combo = _account_combo(accounts)
        self.field(i18n.tr("bank_account"), self.account_combo)
        self.note_edit = QLineEdit()
        self.field(i18n.tr("notes"), self.note_edit)
        ok, _cancel = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    def values(self) -> dict:
        return dict(
            txn_date=self.date_edit.date().toPython(),
            amount=self.amount_spin.value(),
            bank_account_id=self.account_combo.currentData(),
            notes=self.note_edit.text().strip(),
        )


class LoansScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        can = has_permission(current_user.role, Permission.MANAGE_PAYMENTS)

        root = QVBoxLayout(self)
        # Side inset so tiles / search / table sit off the panel's rounded
        # edge, consistent with the other pages.
        root.setContentsMargins(22, 8, 22, 14)
        root.setSpacing(12)

        design.refresh()
        totals = QHBoxLayout()
        totals.setSpacing(14)
        taken_tile, self.taken_label = design.stat_tile(
            i18n.tr("loans_taken"), design.NEG, "hand-coins")
        given_tile, self.given_label = design.stat_tile(
            i18n.tr("loans_given"), design.POS, "hand-coins")
        totals.addWidget(taken_tile, 1)
        totals.addWidget(given_tile, 1)
        totals.addStretch(2)
        root.addLayout(totals)

        self.table = make_table([
            i18n.tr("date"), i18n.tr("loan_direction"), i18n.tr("person_name"),
            i18n.tr("principal"), i18n.tr("repaid"), i18n.tr("outstanding"),
            i18n.tr("bank_account"), i18n.tr("expected_return"),
        ])
        self.search = SearchBox(self.table)
        root.addWidget(self.search)
        root.addWidget(self.table)

        buttons = QHBoxLayout()
        self.manage_btn = design.manage_button([
            (i18n.tr("add"), self._borrow, "plus"),
            (i18n.tr("repay_loan"), self._repay, "hand-coins"),
            None,
            (i18n.tr("delete"), self._delete, "trash", "danger"),
        ], parent=self)
        self.manage_btn.setEnabled(can)
        buttons.addWidget(self.manage_btn)
        buttons.addStretch()
        root.addWidget(design.toolbar_wrap(buttons))

        self.refresh()

    def refresh(self) -> None:
        from timber.db.models.loan import LOAN_GIVEN

        with SessionLocal() as session:
            rows = loan_service.list_loans(session)
            taken = loan_service.total_loans_outstanding(session)
            given = loan_service.total_loans_outstanding(session, LOAN_GIVEN)
        self._ids = [r.id for r in rows]
        self._outstanding = [r.outstanding for r in rows]
        self._directions = [r.direction for r in rows]
        dir_names = {
            "taken": i18n.tr("loan_taken"), "given": i18n.tr("loan_given"),
        }
        fill_table(self.table, [
            [
                str(r.txn_date), dir_names.get(r.direction, r.direction),
                r.lender_name, fmt(r.principal), fmt(r.repaid),
                fmt(r.outstanding), r.account_name,
                str(r.expected_return_date) if r.expected_return_date else "",
            ]
            for r in rows
        ])
        for i, r in enumerate(rows):
            if r.outstanding <= 0:
                colour = "#16a34a"          # settled
            elif r.direction == LOAN_GIVEN:
                colour = "#16a34a"          # they owe us -> receive (green)
            else:
                colour = "#c62828"          # we owe -> give (red)
            colour_cell(self.table, i, 5, colour)
        self.search.apply()
        # Sign rule: to give = negative (red), to receive = positive (green).
        self.taken_label.setText(fmt(-taken))
        self.given_label.setText(fmt(given))

    def _borrow(self) -> None:
        dialog = LoanDialog(_accounts(), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        v = dialog.values()
        try:
            with SessionLocal() as session:
                loan_service.create_loan(session, created_by=self.current_user.id, **v)
                # Strict rule: lending money out can't overdraw the account.
                if v.get("direction") == "given":
                    from timber.core.bank_service import ensure_not_overdrawn
                    ensure_not_overdrawn(session, v.get("bank_account_id"))
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _selected_row(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("loans"), i18n.tr("select_item"))
            return None
        return row

    def _repay(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        dialog = RepayDialog(_accounts(), self._outstanding[row], parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        v = dialog.values()
        try:
            with SessionLocal() as session:
                loan_service.repay_loan(
                    session, loan_id=self._ids[row], created_by=self.current_user.id,
                    **v,
                )
                # Repaying a TAKEN loan sends money out — never overdraw.
                if self._directions[row] != "given":
                    from timber.core.bank_service import ensure_not_overdrawn
                    ensure_not_overdrawn(session, v.get("bank_account_id"))
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _delete(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        if not design.confirm(self, i18n.tr("delete"), i18n.tr("confirm_delete"), danger=True):
            return
        with SessionLocal() as session:
            loan_service.delete_loan(session, self._ids[row], created_by=self.current_user.id)
            session.commit()
            info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        self.refresh()
