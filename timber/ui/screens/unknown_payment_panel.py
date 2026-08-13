"""Unknown receipts panel — record money that arrived with no known sender,
and CLAIM it to a party once someone owns up (we verify by choosing them).
Lives as the third tab on the Payment screen.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QSizePolicy,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber import i18n
from timber.ui import design, icons
from timber.core import unknown_payment_service as ups
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.db.engine import SessionLocal
from timber.db.models import BankAccount, Party
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import (
    METHOD_BANK,
    METHOD_CASH,
    METHOD_CHEQUE,
    METHOD_ONLINE,
    PAYMENT_IN,
    PAYMENT_OUT,
)
from timber.ui.screens.table_utils import (
    BAL_RED,
    SearchBox,
    attach_words,
    colour_cell,
    fill_table,
    fmt,
    make_table,
    stat_card,
    words_label,
)
from timber.ui.searchable import SearchableComboBox
from timber.ui.toast import info_toast, warn_toast

_METHODS = [
    ("online", METHOD_ONLINE),
    ("bank", METHOD_BANK),
    ("cash", METHOD_CASH),
    ("cheque", METHOD_CHEQUE),
]

_AMBER = "#d97706"


def _age_colour(days: int) -> str:
    if days >= 30:
        return BAL_RED
    if days >= 14:
        return _AMBER
    return "#64748b"


class _ClaimDialog(design.Dialog):
    """Pick which party a mystery receipt belongs to (the 'verify' step).
    Shows the receipt's details and the chosen party's live balance."""

    def __init__(self, row, parent=None) -> None:
        super().__init__(i18n.tr("claim_to_party"), "help-circle",
                         parent=parent, width=520)
        root = self.body

        # A little receipt summary at the top.
        summary = QLabel(
            f"<b>{fmt(row.amount)}</b> · {row.account_name} · {row.txn_date}"
            + (f" · {row.reference}" if row.reference else "")
        )
        # Was hard-coded indigo-on-white: unreadable in dark mode.
        summary.setStyleSheet(
            f"background:{design.tint(design.c('accent'), 34)};"
            f"color:{design.c('text')};border-radius:9px;padding:11px 13px;"
        )
        summary.setWordWrap(True)
        # A word-wrapped QLabel still reports its FULL unwrapped width as its
        # size hint, which dragged the whole dialog body out to ~960px and
        # pushed the left-hand labels off screen. Ignoring its width hint lets
        # it wrap to whatever the dialog actually gives it.
        summary.setSizePolicy(QSizePolicy.Policy.Ignored,
                              QSizePolicy.Policy.Minimum)
        summary.setMinimumWidth(1)
        root.addWidget(summary)

        form = QFormLayout()
        # Without these the field column grows past the dialog edge: the
        # balance label was laid out 710px wide inside a 480px box, so the
        # left labels were pushed out of view.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        self.party_combo = SearchableComboBox(i18n.tr("search"))
        with SessionLocal() as session:
            # Factories first (the usual claimant), then suppliers, each labelled.
            for ptype, tag in (
                (PARTY_FACTORY, i18n.tr("factory")),
                (PARTY_BAPARI, i18n.tr("bapari")),
            ):
                for p in session.scalars(
                    select(Party).where(
                        Party.party_type == ptype, Party.is_active.is_(True)
                    ).order_by(Party.name)
                ):
                    self.party_combo.addItem(f"{p.name}  ({tag})", p.id)
        self.party_combo.setCurrentIndex(-1)
        self.party_combo.currentIndexChanged.connect(self._show_balance)
        form.addRow(i18n.tr("who_sent"), self.party_combo)

        self.balance_label = QLabel("—")
        self.balance_label.setStyleSheet("font-weight:bold; color:#64748b;")
        form.addRow(i18n.tr("current_balance"), self.balance_label)
        root.addLayout(form)

        ok, _cancel = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    def _show_balance(self) -> None:
        from timber.core.ledger import party_balance
        from timber.ui.screens.table_utils import bal_colour, bal_text

        pid = self.party_combo.currentData()
        if not pid:
            self.balance_label.setText("—")
            self.balance_label.setStyleSheet("font-weight:bold; color:#64748b;")
            return
        with SessionLocal() as session:
            party = session.get(Party, pid)
            is_supplier = party.party_type == PARTY_BAPARI
            bal = party_balance(session, pid)
        self.balance_label.setText(bal_text(is_supplier, bal))
        self.balance_label.setStyleSheet(
            f"font-weight:bold; color:{bal_colour(is_supplier, bal)};"
        )

    def party_id(self):
        return self.party_combo.currentData()


class UnknownPaymentPanel(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        can = has_permission(current_user.role, Permission.MANAGE_PAYMENTS)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # -- heading ---------------------------------------------------
        # The explanatory hint line under this heading is gone: the section
        # title already says what it is, and the paragraph only pushed the
        # receipts list further down.
        title = QLabel(i18n.tr("unknown_receipts"))
        title.setStyleSheet(
            f"color:{design.c('text')};font-size:15px;font-weight:800;"
            "margin:0;padding:0;")
        title.setFixedHeight(20)          # no stray leading above/below
        root.addWidget(title, 0, Qt.AlignmentFlag.AlignLeft)

        # -- KPI cards (rebuilt each refresh) --------------------------
        self.cards_box = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_box)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        # Size to the tallest card, but never STRETCH with the panel (which
        # was most of the vertical bulk). A hard pixel height clipped the card
        # that carries a subtitle — and would clip again in another language,
        # so let the content decide and only pin the policy.
        self.cards_box.setSizePolicy(
            self.cards_box.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Fixed,
        )
        root.addWidget(self.cards_box)

        # -- record form -----------------------------------------------
        # A grid keeps every field on one row (the sub-labels for amount /
        # available sit on a row below, so nothing gets pushed down).
        # A modal box, opened by the button — the same shape as Add/Edit on
        # Master Data. Built once; its field handlers are untouched.
        self._record_dlg = design.Dialog(
            i18n.tr("record_receipt"), "wallet", parent=self, width=820)

        # Direction gets its OWN row above the fields. As a sixth grid column
        # it pushed the row past the dialog edge (and further in Urdu, where
        # the labels are longer) — and it reads better here anyway: it is a
        # mode switch that changes what every field below means.
        from timber.ui.segmented import SegmentedControl

        self.dir_seg = SegmentedControl(
            [(PAYMENT_IN, i18n.tr("dir_money_in"), ""),
             (PAYMENT_OUT, i18n.tr("dir_money_out"), "")],
            current=PAYMENT_IN, compact=True,
        )
        dir_row = QWidget()
        dir_layout = QHBoxLayout(dir_row)
        dir_layout.setContentsMargins(16, 14, 16, 0)
        dir_layout.setSpacing(10)
        dir_cap = QLabel(i18n.tr("payment_dir"))
        dir_cap.setStyleSheet("font-size:11px; color:#64748b;")
        dir_layout.addWidget(dir_cap)
        dir_layout.addWidget(self.dir_seg)
        dir_layout.addStretch(1)
        self._record_dlg.add(dir_row)

        box = QWidget()
        self._record_dlg.add(box)
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)
        grid.setContentsMargins(16, 18, 16, 18)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setDecimals(2)
        self.amount_spin.setMaximum(1_000_000_000.0)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_words = words_label()
        attach_words(self.amount_spin, self.amount_words)
        self.account_combo = QComboBox()
        self.avail_label = QLabel("")
        self.avail_label.setStyleSheet(f"color:{design.c('accent')};font-size:11px;")
        self.method_combo = QComboBox()
        for key, val in _METHODS:
            self.method_combo.addItem(i18n.tr(key), val)
        self.ref_edit = QLineEdit()
        self.ref_edit.setPlaceholderText(i18n.tr("reference"))
        fields = [
            ("date", self.date_edit, None),
            ("amount", self.amount_spin, self.amount_words),
            ("bank_account", self.account_combo, self.avail_label),
            ("method", self.method_combo, None),
            ("reference", self.ref_edit, None),
        ]
        for col, (lbl, widget, extra) in enumerate(fields):
            cap = QLabel(i18n.tr(lbl))
            cap.setStyleSheet("font-size:11px; color:#64748b;")
            grid.addWidget(cap, 0, col)                      # captions row
            grid.addWidget(widget, 1, col)                   # fields row (aligned)
            if extra is not None:
                grid.addWidget(extra, 2, col)                # sub-labels row
        self.record_btn = QPushButton(i18n.tr("save"))
        self.record_btn.setStyleSheet(design.btn("primary"))
        self.record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_btn.clicked.connect(self._record)
        self.record_btn.setEnabled(can)
        self._record_dlg.add_button(self.record_btn)
        # Columns: 0 date | 1 amount | 2 account | 3 method | 4 reference
        grid.setColumnStretch(1, 2)   # amount
        grid.setColumnStretch(2, 1)   # bank account
        grid.setColumnStretch(4, 3)   # reference (widest)
        self.toggle_form_btn = QPushButton(i18n.tr("record_receipt"))
        self.toggle_form_btn.setStyleSheet(design.btn("primary"))
        self.toggle_form_btn.setIcon(icons.icon("plus", "#ffffff", 15))
        self.toggle_form_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_form_btn.setEnabled(can)
        # NB: this button is placed further down, inside the search/actions
        # bar — one row instead of two, which is a whole strip of height back
        # for the receipts list.

        def _toggle_form(_=False):
            self.amount_spin.setValue(0)
            self.ref_edit.clear()
            # Reopen on the common case: an unexplained debit is rare and must
            # not become the default for the next entry.
            self.dir_seg.set_current(PAYMENT_IN)
            self._record_dlg.show()
            self._record_dlg.raise_()
            self.amount_spin.setFocus()

        self.toggle_form_btn.clicked.connect(_toggle_form)
        self._toggle_form = _toggle_form

        # Smooth data-entry flow:
        #  * method = cash auto-jumps to the Cash account,
        #  * picking an account shows its balance and moves on to Reference,
        #  * Enter in Reference records the receipt.
        self._cash_account_id = None
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        self.account_combo.currentIndexChanged.connect(self._on_account_changed)
        self.account_combo.activated.connect(lambda _i: self.ref_edit.setFocus())
        self.ref_edit.returnPressed.connect(self._record)

        # -- list + actions --------------------------------------------
        self.table = make_table([
            i18n.tr("date"), i18n.tr("amount"), i18n.tr("bank_account"),
            i18n.tr("method"), i18n.tr("reference"), i18n.tr("age_days"),
            i18n.tr("notes"),
        ])
        bar = QHBoxLayout()
        bar.setSpacing(9)
        bar.addWidget(self.toggle_form_btn)     # record | search | claim | void
        self.search = SearchBox(self.table)
        bar.addWidget(self.search, stretch=1)
        self.claim_btn = QPushButton("✔  " + i18n.tr("claim"))
        self.claim_btn.setStyleSheet(design.btn("success"))
        self.void_btn = QPushButton("✕  " + i18n.tr("void"))
        self.void_btn.setStyleSheet(design.btn("danger"))
        self.claim_btn.clicked.connect(self._claim)
        self.void_btn.clicked.connect(self._void)
        for b in (self.claim_btn, self.void_btn):
            b.setEnabled(can)
            bar.addWidget(b)
        root.addWidget(design.toolbar_wrap(bar))

        self.empty_label = design.empty_state(i18n.tr("no_unknown"), "", "inbox")
        root.addWidget(self.empty_label)
        root.addWidget(self.table)

        self.refresh()

    # -- data -----------------------------------------------------------
    def _clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_cards(self, rows, total) -> None:
        self._clear_cards()
        count = len(rows)
        today = date.today()
        oldest_days = max(((today - r.txn_date).days for r in rows), default=0)
        largest = max((r.amount for r in rows), default=0)
        cards = [
            stat_card(i18n.tr("unclaimed_total"), fmt(total), "#7c3aed",
                      f"{count} {i18n.tr('receipts_waiting')}", "inbox"),
            stat_card(i18n.tr("oldest_waiting"), f"{oldest_days} {i18n.tr('days_short')}",
                      _age_colour(oldest_days), "", "alarm-clock"),
            stat_card(i18n.tr("largest_receipt"), fmt(largest), "#0d9488", "",
                      "trending-up"),
        ]
        for c in cards:
            self.cards_layout.addWidget(c, stretch=1)

    def refresh(self) -> None:
        from timber.core.bank_service import CASH_ACCOUNT_NAME

        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        self._cash_account_id = None
        with SessionLocal() as session:
            accts = session.scalars(
                select(BankAccount).where(BankAccount.is_active.is_(True))
                .order_by(BankAccount.name)
            ).all()
            for a in accts:
                self.account_combo.addItem(a.name, a.id)
                if a._name == CASH_ACCOUNT_NAME:
                    self._cash_account_id = a.id
            rows = ups.list_unknown_payments(session)
            total = ups.total_unknown(session)
        self.account_combo.blockSignals(False)
        self._on_account_changed()

        self._ids = [r.id for r in rows]
        self._rows = rows
        self._amounts = [r.amount for r in rows]
        self._build_cards(rows, total)

        today = date.today()
        fill_table(self.table, [
            [str(r.txn_date), fmt(r.amount), r.account_name,
             i18n.tr(r.method), r.reference, str((today - r.txn_date).days), r.notes]
            for r in rows
        ])
        for i, r in enumerate(rows):
            colour_cell(self.table, i, 5, _age_colour((today - r.txn_date).days))
        self.search.apply()

        has_rows = bool(rows)
        self.table.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)

    live_refresh = refresh

    def _on_method_changed(self) -> None:
        # Cash receipts land in the Cash account automatically.
        if self.method_combo.currentData() == METHOD_CASH and self._cash_account_id:
            idx = self.account_combo.findData(self._cash_account_id)
            if idx >= 0:
                self.account_combo.setCurrentIndex(idx)

    def _on_account_changed(self) -> None:
        from timber.core import bank_service

        acc_id = self.account_combo.currentData()
        if not acc_id:
            self.avail_label.setText("")
            return
        with SessionLocal() as session:
            bal = bank_service.account_balance(session, acc_id)
        colour = BAL_RED if bal < 0 else "#1565c0"
        self.avail_label.setStyleSheet(f"color:{colour}; font-size:11px;")
        self.avail_label.setText(f"{i18n.tr('available')}: {bal:,.2f}")

    def _selected(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("claim"), i18n.tr("select_item"))
            return None
        return row

    def _record(self) -> None:
        try:
            with SessionLocal() as session:
                ups.create_unknown_payment(
                    session,
                    txn_date=self.date_edit.date().toPython(),
                    amount=self.amount_spin.value(),
                    direction=self.dir_seg.current(),
                    bank_account_id=self.account_combo.currentData(),
                    method=self.method_combo.currentData(),
                    reference_no=self.ref_edit.text().strip(),
                    created_by=self.current_user.id,
                )
                # An unexplained DEBIT is real money leaving, so it must not
                # push the account negative any more than a payment out would.
                if self.dir_seg.current() == PAYMENT_OUT:
                    from timber.core.bank_service import ensure_not_overdrawn
                    ensure_not_overdrawn(session, self.account_combo.currentData())
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.amount_spin.setValue(0)
        self.ref_edit.clear()
        info_toast(self, i18n.tr("added_ok"), i18n.tr("added_ok"))
        dlg = getattr(self, "_record_dlg", None)
        if dlg is not None:
            dlg.accept()          # the box closes once the receipt is in
        self.refresh()

    def _claim(self) -> None:
        row = self._selected()
        if row is None:
            return
        dlg = _ClaimDialog(self._rows[row], parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with SessionLocal() as session:
                ups.claim_unknown_payment(
                    session, self._ids[row], dlg.party_id(),
                    created_by=self.current_user.id,
                )
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        self.refresh()

    def _void(self) -> None:
        row = self._selected()
        if row is None:
            return
        with SessionLocal() as session:
            ups.void_unknown_payment(
                session, self._ids[row], created_by=self.current_user.id
            )
            session.commit()
        info_toast(self, i18n.tr("removed_ok"), i18n.tr("removed_ok"))
        self.refresh()
