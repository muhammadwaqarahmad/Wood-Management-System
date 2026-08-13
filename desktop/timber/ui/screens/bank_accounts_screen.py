"""Business bank accounts — list with live balances, add/edit/deactivate."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design
from timber.core import bank_service
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, Role, has_permission
from timber.db.engine import SessionLocal
from timber.db.models import BankAccount
from timber.ui.screens.export_helpers import export_buttons
from timber.ui.screens.table_utils import SearchBox, fill_table, fmt, make_table


class BankAccountDialog(design.Dialog):
    def __init__(self, account=None, parent=None, can_edit_opening: bool = True) -> None:
        super().__init__(i18n.tr("edit") if account else i18n.tr("add"), "landmark", parent=parent, width=500)
        # Bilingual name: the account shows in each user's own language.
        self.name_en_edit = QLineEdit(account.name_en if account and account.name_en else "")
        self.field(i18n.tr("name_en"), self.name_en_edit)
        self.name_ur_edit = QLineEdit(account.name_ur if account and account.name_ur else "")
        self.field(i18n.tr("name_ur"), self.name_ur_edit)
        self.bank_edit = QLineEdit(account.bank_name if account and account.bank_name else "")
        self.field(i18n.tr("bank_name"), self.bank_edit)
        self.acc_no_edit = QLineEdit(
            account.account_number if account and account.account_number else ""
        )
        self.field(i18n.tr("account_number"), self.acc_no_edit)
        self.iban_edit = QLineEdit(account.iban if account and account.iban else "")
        self.iban_edit.setMaxLength(24)
        self.field(i18n.tr("iban"), self.iban_edit)

        self.branch_edit = QLineEdit(account.branch if account and account.branch else "")
        self.field(i18n.tr("branch"), self.branch_edit)

        self.opening_spin = QDoubleSpinBox()
        self.opening_spin.setDecimals(2)
        self.opening_spin.setRange(0.0, 1_000_000_000.0)  # opening can't be negative
        if account:
            self.opening_spin.setValue(float(account.opening_balance))
        # The opening balance anchors the whole account history — Admin only.
        self.opening_spin.setEnabled(can_edit_opening)
        if not can_edit_opening:
            self.opening_spin.setToolTip(i18n.tr("opening_admin_only"))
        self.field(i18n.tr("opening_balance"), self.opening_spin)

        ok, _cancel = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    def accept(self) -> None:
        iban = self.iban_edit.text().strip()
        if iban and len(iban) != 24:
            warn_toast(
                self, i18n.tr("cannot_save"), i18n.tr("iban_len_error")
            )
            return
        super().accept()

    def values(self) -> dict:
        return dict(
            name_en=self.name_en_edit.text().strip(),
            name_ur=self.name_ur_edit.text().strip(),
            bank_name=self.bank_edit.text().strip(),
            account_number=self.acc_no_edit.text().strip(),
            iban=self.iban_edit.text().strip(),
            branch=self.branch_edit.text().strip(),
            opening_balance=self.opening_spin.value(),
        )


class BankAccountsScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user

        root = QVBoxLayout(self)
        # Side inset so KPI tiles / table sit off the panel's rounded edge,
        # consistent with the Dashboard and Reports pages.
        root.setContentsMargins(22, 8, 22, 14)
        root.setSpacing(12)

        design.refresh()
        totals = QHBoxLayout()
        totals.setSpacing(14)
        total_tile, self.total_label = design.stat_tile(
            i18n.tr("cash_position"), design.c("accent"), "wallet")
        totals.addWidget(total_tile, 1)
        cheque_tile, self.cheque_label = design.stat_tile(
            i18n.tr("cheque_balance"), design.TONES["amber"], "file-check")
        totals.addWidget(cheque_tile, 1)
        loans_tile, self.loans_label = design.stat_tile(
            i18n.tr("total_loans"), design.TONES["violet"], "hand-coins")
        totals.addWidget(loans_tile, 1)
        totals.addStretch(1)
        root.addLayout(totals)

        self.table = make_table(
            [
                i18n.tr("name"),
                i18n.tr("bank_name"),
                i18n.tr("account_number"),
                i18n.tr("iban"),
                i18n.tr("branch"),
                i18n.tr("opening_today"),
                i18n.tr("closing"),
            ]
        )
        self.search = SearchBox(self.table)
        root.addWidget(self.search)
        root.addWidget(self.table)

        buttons = QHBoxLayout()
        self.manage_btn = design.manage_button([
            (i18n.tr("add"), self._add, "plus"),
            (i18n.tr("edit"), self._edit, "pencil"),
        ], parent=self)
        buttons.addWidget(self.manage_btn)
        buttons.addStretch()
        # Export every account's bank book (PDF / Excel).
        for b in export_buttons(self, self._build_report, "bank_book", as_widgets=True):
            buttons.addWidget(b)
        root.addWidget(design.toolbar_wrap(buttons))

        self.manage_btn.setEnabled(
            has_permission(current_user.role, Permission.MANAGE_SETTINGS)
        )

        self.refresh()

    def refresh(self) -> None:
        from datetime import date as _date

        from timber.core import loan_service, payment_service
        today = _date.today()
        with SessionLocal() as session:
            balances = bank_service.all_balances(session, active_only=False)
            # Reuse the balances just computed instead of redoing them all.
            total = bank_service.total_cash_position(session, balances)
            cheque_bal = payment_service.cheque_balance(session)
            loans = loan_service.total_loans_outstanding(session)
            # Today's opening = yesterday's closing — rolls forward every
            # day and with every payment/expense/transfer, like the paper
            # book (not the account's original configured opening). ONE
            # batched call for every account, not one query per account.
            openings = bank_service.all_account_balances(session, before=today)
        self._ids = [b.id for b in balances]
        fill_table(
            self.table,
            [
                [
                    b.name, b.bank_name or "", b.account_number or "",
                    b.iban or "", b.branch or "",
                    fmt(openings.get(b.id, b.opening)), fmt(b.closing),
                ]
                for b in balances
            ],
        )
        self.search.apply()
        self.total_label.setText(fmt(total))
        self.cheque_label.setText(fmt(cheque_bal))
        self.loans_label.setText(fmt(loans))

    def _build_report(self):
        """Every account's bank book (date/opening/in/out/closing) — balances
        already live in Financial Position, so this exports the movements."""
        from timber.core.report_data import all_bank_books_report
        with SessionLocal() as session:
            return all_bank_books_report(session)

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("edit"), i18n.tr("select_item"))
            return None
        return self._ids[row]

    def _add(self) -> None:
        dialog = BankAccountDialog(
            parent=self,
            can_edit_opening=self.current_user.role == Role.ADMIN.value,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with SessionLocal() as session:
                bank_service.create_account(
                    session, created_by=self.current_user.id, **dialog.values()
                )
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _edit(self) -> None:
        account_id = self._selected_id()
        if account_id is None:
            return
        with SessionLocal() as session:
            account = session.get(BankAccount, account_id)
            dialog = BankAccountDialog(
                account=account, parent=self,
                can_edit_opening=self.current_user.role == Role.ADMIN.value,
            )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with SessionLocal() as session:
                bank_service.update_account(
                    session, account_id, created_by=self.current_user.id, **dialog.values()
                )
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()
