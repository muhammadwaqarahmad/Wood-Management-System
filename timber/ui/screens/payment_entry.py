"""Payment page — Factory and Bapari tabs.

Factory tab records money RECEIVED from factories (reduces what they
owe you). Bapari tab records money PAID to baparis (reduces what you
owe them). Each updates the chosen bank account and the party ledger,
and shows a searchable history with void.
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
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design, icons
from timber.ui.segmented import SegmentedControl
from timber.core.current_user import CurrentUser
from timber.core.ledger import party_balance
from timber.core.payment_service import (
    create_payment,
    list_payments,
    party_bank_label,
    party_outstanding_loads,
    update_payment,
    void_payment,
)
from timber.core.permissions import Permission, has_permission
from timber.db.engine import SessionLocal
from timber.db.models import BankAccount, Party
from timber.db.models import Payment as _Payment
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.db.models.payment import (
    METHOD_BANK,
    METHOD_CASH,
    METHOD_CHEQUE,
    METHOD_ONLINE,
    PAYMENT_IN,
    PAYMENT_OUT,
    natural_direction,
)
from timber.ui.screens.table_utils import (
    attach_words,
    bal_colour,
    bal_text,
    fill_table,
    filter_table,
    fmt,
    make_table,
    progress_cell,
    words_label,
)

_METHODS = [
    ("cash", METHOD_CASH),
    ("online", METHOD_ONLINE),
    ("bank", METHOD_BANK),
    ("cheque", METHOD_CHEQUE),
]


class _PaymentEditDialog(design.Dialog):
    """Edit an existing payment (party stays the same)."""

    def __init__(self, accounts, party_banks, data, party_type, parent=None) -> None:
        super().__init__(i18n.tr("edit"), "wallet", parent=parent, width=520)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        d = data["txn_date"]
        self.date_edit.setDate(QDate(d.year, d.month, d.day))
        self.field(i18n.tr("date"), self.date_edit)

        # Direction is editable here too — otherwise a payment entered the
        # wrong way round could only be fixed by voiding and re-entering it.
        from timber.ui.segmented import SegmentedControl

        self.dir_seg = SegmentedControl(
            [(PAYMENT_OUT, i18n.tr("dir_money_out"), ""),
             (PAYMENT_IN, i18n.tr("dir_money_in"), "")],
            current=data.get("direction") or natural_direction(party_type),
            compact=True,
        )
        self.field(i18n.tr("payment_dir"), self.dir_seg)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setDecimals(2)
        self.amount_spin.setMaximum(1_000_000_000.0)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setValue(data["amount"])
        self.field(i18n.tr("amount"), self.amount_spin)

        self.method_combo = QComboBox()
        for key, val in _METHODS:
            self.method_combo.addItem(i18n.tr(key), val)
        mi = self.method_combo.findData(data["method"])
        if mi >= 0:
            self.method_combo.setCurrentIndex(mi)
        self.field(i18n.tr("method"), self.method_combo)

        self.account_combo = QComboBox()
        for aid, aname in accounts:
            self.account_combo.addItem(aname, aid)
        ai = self.account_combo.findData(data["bank_account_id"])
        if ai >= 0:
            self.account_combo.setCurrentIndex(ai)
        self.field(i18n.tr("bank_account"), self.account_combo)

        self.party_bank_combo = QComboBox()
        self.party_bank_combo.addItem("—", None)
        for bid, label in party_banks:
            self.party_bank_combo.addItem(label, bid)
        pi = self.party_bank_combo.findData(data["party_bank_id"])
        if pi >= 0:
            self.party_bank_combo.setCurrentIndex(pi)
        self.field(f"{i18n.tr(party_type)} {i18n.tr('account')}",
                   self.party_bank_combo)

        self.reference_edit = QLineEdit(data["reference_no"])
        self.field(i18n.tr("reference"), self.reference_edit)
        self.notes_edit = QLineEdit(data["notes"])
        self.field(i18n.tr("notes"), self.notes_edit)

        ok, _cancel = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    def values(self) -> dict:
        return dict(
            txn_date=self.date_edit.date().toPython(),
            direction=self.dir_seg.current(),
            amount=self.amount_spin.value(),
            method=self.method_combo.currentData(),
            bank_account_id=self.account_combo.currentData(),
            party_bank_id=self.party_bank_combo.currentData(),
            reference_no=self.reference_edit.text().strip(),
            notes=self.notes_edit.text().strip(),
        )


class PaymentPanel(QWidget):
    def __init__(self, current_user: CurrentUser, party_type: str, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        self.party_type = party_type
        can = has_permission(current_user.role, Permission.MANAGE_PAYMENTS)

        self._can = can
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("content")
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setSpacing(12)

        # ===== Record payment (form) =====
        # The form is tall, which pushed the saved payments far down the page.
        # It now collapses behind a button and starts closed, so the history is
        # the first thing visible; recording is one click away.
        self.toggle_form_btn = QPushButton(i18n.tr("record_payment"))
        self.toggle_form_btn.setStyleSheet(design.btn("primary"))
        self.toggle_form_btn.setIcon(icons.icon("plus", "#ffffff", 15))
        self.toggle_form_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_form_btn.setEnabled(can)
        # Placed further down, inside the records filter bar — one row rather
        # than two, which gives the payment list back a strip of height.

        # The form is a modal box, opened by the button — the same shape as
        # Add/Edit on Master Data. Built ONCE here (all its field handlers
        # stay exactly as they were) and re-shown on each click.
        self._record_dlg = design.Dialog(
            i18n.tr("record_payment"), "wallet",
            i18n.tr(party_type), parent=self, width=860,
        )
        rb = self._record_dlg.body

        # Build the fields.
        from timber.ui.searchable import SearchableComboBox

        self.party_combo = SearchableComboBox(i18n.tr("search"))
        self.party_combo.currentIndexChanged.connect(self._show_balance)
        self.balance_label = QLabel("—")
        self.balance_label.setStyleSheet(
            f"font-size:16px;font-weight:800;color:{design.c('accent')};")
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setDecimals(2)
        self.amount_spin.setMaximum(1_000_000_000.0)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_words = words_label()
        attach_words(self.amount_spin, self.amount_words)
        amt_box = QVBoxLayout()
        amt_box.setSpacing(2)
        amt_box.addWidget(self.amount_spin)
        amt_box.addWidget(self.amount_words)
        # Which way the money moved. Normally out to a supplier and in from a
        # factory, so that is preselected — but the reverse is a real event
        # (a supplier refunding rejected wood, us refunding a factory) and the
        # ledger now handles it, so it has to be selectable.
        from timber.ui.segmented import SegmentedControl

        self._natural_dir = natural_direction(party_type)
        self.dir_seg = SegmentedControl(
            [(PAYMENT_OUT, i18n.tr("dir_money_out"), ""),
             (PAYMENT_IN, i18n.tr("dir_money_in"), "")],
            current=self._natural_dir, compact=True,
        )
        self.dir_hint = QLabel("")
        self.dir_hint.setStyleSheet(
            f"color:{design.c('muted')};font-size:11px;")
        self.dir_seg.changed.connect(lambda *_: self._on_direction_changed())
        dir_box = QVBoxLayout()
        dir_box.setSpacing(2)
        dir_box.addWidget(self.dir_seg)
        dir_box.addWidget(self.dir_hint)

        self.method_combo = QComboBox()
        for key, value in _METHODS:
            self.method_combo.addItem(i18n.tr(key), value)
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        self.account_combo = QComboBox()
        self.account_combo.currentIndexChanged.connect(self._on_account_changed)
        self.account_avail_label = QLabel("")
        self.account_avail_label.setStyleSheet(
            f"color:{design.c('accent')};font-size:11px;")
        acct_box = QVBoxLayout()
        acct_box.setSpacing(2)
        acct_box.addWidget(self.account_combo)
        acct_box.addWidget(self.account_avail_label)
        self.party_bank_combo = QComboBox()  # the bapari's / factory's own account
        self.reference_edit = QLineEdit()
        self.notes_edit = QLineEdit()

        # Factory split sub-ledger: which side this payment settles. Shown
        # only when the selected factory has a split_rate set.
        self.side_combo = QComboBox()
        self.side_combo.addItem(i18n.tr("side_left"), "left")
        self.side_combo.addItem(i18n.tr("side_right"), "right")
        self._side_label = QLabel(i18n.tr("split_side"))
        self._side_label.setVisible(False)
        self.side_combo.setVisible(False)

        # Two columns: the party's side (who we deal with) and OUR side
        # (how the money moves from/to us).
        cols = QHBoxLayout()
        cols.setSpacing(20)

        party_box = QGroupBox(i18n.tr(party_type))
        left_form = QFormLayout(party_box)
        left_form.setVerticalSpacing(10)
        left_form.addRow(i18n.tr("date"), self.date_edit)
        left_form.addRow(i18n.tr("name"), self.party_combo)
        left_form.addRow(i18n.tr("current_balance"), self.balance_label)
        party_acc_label = f"{i18n.tr(party_type)} {i18n.tr('account')}"
        left_form.addRow(party_acc_label, self.party_bank_combo)
        left_form.addRow(self._side_label, self.side_combo)

        ours_box = QGroupBox(i18n.tr("payer_us"))
        right_form = QFormLayout(ours_box)
        right_form.setVerticalSpacing(10)
        right_form.addRow(i18n.tr("payment_dir"), dir_box)
        right_form.addRow(i18n.tr("amount"), amt_box)
        right_form.addRow(i18n.tr("method"), self.method_combo)
        right_form.addRow(i18n.tr("bank_account"), acct_box)
        right_form.addRow(i18n.tr("reference"), self.reference_edit)

        cols.addWidget(party_box, stretch=1)
        cols.addWidget(ours_box, stretch=1)
        rb.addLayout(cols)

        self.save_btn = QPushButton(i18n.tr("save"))
        self.save_btn.setStyleSheet(design.btn("primary"))
        self.save_btn.setIcon(icons.icon("check", "#ffffff", 15))
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setEnabled(can)
        self.save_btn.setMinimumWidth(160)
        # Save sits in the dialog's own footer, beside Cancel.
        self.save_btn.setMinimumWidth(140)
        self._record_dlg.add_button(self.save_btn)

        self._on_direction_changed()

        def _open_form(_=False):
            self.party_combo.setCurrentIndex(-1)
            self.amount_spin.setValue(0)
            self.reference_edit.clear()
            self.notes_edit.clear()
            # Always reopen on the common case, so a one-off refund cannot
            # silently become the default for the next entry.
            self.dir_seg.set_current(self._natural_dir)
            self._on_direction_changed()
            self._record_dlg.show()
            self._record_dlg.raise_()
            self.party_combo.setFocus()

        self.toggle_form_btn.clicked.connect(_open_form)
        self._open_form = _open_form

        # ===== Records: view + date filter + search on top =====
        records_box = QWidget()
        recb = QVBoxLayout(records_box)
        recb.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        bar.addWidget(self.toggle_form_btn)     # record | filters | search | actions
        bar.addWidget(QLabel(f"{i18n.tr('show')}:"))
        self.view_combo = QComboBox()
        self.view_combo.addItem(i18n.tr("payment_history"), "history")
        self.view_combo.addItem(i18n.tr("outstanding_loads"), "outstanding")
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        bar.addWidget(self.view_combo)

        bar.addWidget(QLabel(f"{i18n.tr('period')}:"))
        self.period_combo = QComboBox()
        for key in ("day", "week", "month", "year", "custom", "all"):
            self.period_combo.addItem(i18n.tr(key), key)
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        bar.addWidget(self.period_combo)
        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("yyyy-MM-dd")
        self.from_date.setDate(QDate.currentDate())
        self.from_date.dateChanged.connect(self.refresh)
        bar.addWidget(self.from_date)
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setDate(QDate.currentDate())
        self.to_date.dateChanged.connect(self.refresh)
        bar.addWidget(self.to_date)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(i18n.tr("search"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        bar.addWidget(self.search_edit, stretch=1)
        self.edit_btn = QPushButton(i18n.tr("edit"))
        self.edit_btn.setStyleSheet(design.btn("ghost"))
        self.edit_btn.setIcon(icons.icon("pencil", design.c("text"), 15))
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.clicked.connect(self._edit)
        self.edit_btn.setEnabled(can)
        bar.addWidget(self.edit_btn)
        self.void_btn = QPushButton(i18n.tr("void"))
        self.void_btn.setStyleSheet(design.btn("danger"))
        self.void_btn.setIcon(icons.icon("x", "#ffffff", 15))
        self.void_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.void_btn.clicked.connect(self._void)
        self.void_btn.setEnabled(can)
        bar.addWidget(self.void_btn)
        recb.addWidget(design.toolbar_wrap(bar))

        self.table = make_table(
            [
                i18n.tr("date"), i18n.tr(party_type), i18n.tr("amount"),
                i18n.tr("method"), i18n.tr("bank_account"),
                f"{i18n.tr(party_type)} {i18n.tr('account')}", i18n.tr("reference"),
            ]
        )
        self.out_table = make_table(
            [
                i18n.tr("date"), i18n.tr("amount"), i18n.tr("paid"),
                i18n.tr("outstanding"), i18n.tr("paid_progress"), i18n.tr("days"),
            ]
        )
        self.stack = QStackedWidget()
        self.stack.setMinimumHeight(360)  # plenty of room for history rows
        self.stack.addWidget(self.table)       # index 0 = history (default)
        self.stack.addWidget(self.out_table)   # index 1 = outstanding
        recb.addWidget(self.stack)
        root.addWidget(records_box, stretch=1)

        # Opens on TODAY, matching the other pages. "All" is one click away.
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentIndex(self.period_combo.findData("day"))
        self.period_combo.blockSignals(False)

        self._on_period_changed()  # sets enabled state + refreshes
        self._on_method_changed()
        self._on_view_changed()

    def _date_range(self):
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
        return anchor, self.to_date.date().toPython()  # custom

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

    def _active_table(self):
        return self.table if self.view_combo.currentData() == "history" else self.out_table

    def _on_view_changed(self) -> None:
        is_history = self.view_combo.currentData() == "history"
        self.stack.setCurrentIndex(0 if is_history else 1)
        self.void_btn.setVisible(is_history)
        self.edit_btn.setVisible(is_history)
        self._apply_filter()

    def _apply_filter(self) -> None:
        filter_table(self._active_table(), self.search_edit.text())

    def refresh(self) -> None:
        from timber.core.bank_service import CASH_ACCOUNT_NAME

        with SessionLocal() as session:
            parties = session.scalars(
                select(Party)
                .where(Party.party_type == self.party_type, Party.is_active.is_(True))
                .order_by(Party.name)
            ).all()
            accounts = session.scalars(
                select(BankAccount).where(BankAccount.is_active.is_(True)).order_by(BankAccount.name)
            ).all()
            self._cash_account_id = next(
                (a.id for a in accounts if a._name == CASH_ACCOUNT_NAME), None
            )
            # EVERY account's balance in one batched pass (a handful of grouped
            # queries) instead of ~8 per account on each selection.
            from timber.core.bank_service import all_account_balances

            self._acct_balances = all_account_balances(session)
            start, end = self._date_range()
            history = list_payments(session, self.party_type, start, end)

        self.party_combo.blockSignals(True)
        self.party_combo.clear()
        for p in parties:
            self.party_combo.addItem(p.name, p.id)
        self.party_combo.setCurrentIndex(-1)  # no party pre-selected
        self.party_combo.lineEdit().clear()
        self.party_combo.blockSignals(False)

        # Block signals while filling: each addItem fires currentIndexChanged,
        # and the handler used to run a full account-balance query EVERY time
        # (8 queries per account -> the screen opened with ~65 queries).
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        for a in accounts:
            self.account_combo.addItem(a.name, a.id)
        self.account_combo.blockSignals(False)
        self._on_account_changed()  # refresh the available-balance hint (once)

        self._ids = [r.id for r in history]
        fill_table(
            self.table,
            [
                [str(r.txn_date), r.party_name, fmt(r.amount), r.method,
                 r.account_name, r.party_account, r.reference]
                for r in history
            ],
        )
        self._show_balance()
        self._apply_filter()

    def live_refresh(self) -> None:
        """Reload ONLY the records list — leaves the entry form + combos
        untouched, so a payment made on another PC shows up here without
        wiping what this user is typing."""
        with SessionLocal() as session:
            start, end = self._date_range()
            history = list_payments(session, self.party_type, start, end)
        self._ids = [r.id for r in history]
        fill_table(
            self.table,
            [
                [str(r.txn_date), r.party_name, fmt(r.amount), r.method,
                 r.account_name, r.party_account, r.reference]
                for r in history
            ],
        )
        self._apply_filter()

    def _show_balance(self) -> None:
        from timber.core.payment_service import party_bank_label
        from timber.db.models import Party as _Party

        party_id = self.party_combo.currentData()
        if not party_id:
            self.balance_label.setText("—")
            self.out_table.setRowCount(0)
            self.party_bank_combo.clear()
            return
        with SessionLocal() as session:
            bal = party_balance(session, party_id)
            loads = party_outstanding_loads(session, party_id)
            party = session.get(_Party, party_id)
            banks = [(b.id, party_bank_label(b)) for b in party.banks]
            split_rate = party.split_rate or 0
        # Side selector only for factories that use the split sub-ledger.
        show_side = self.party_type == PARTY_FACTORY and split_rate > 0
        self._side_label.setVisible(show_side)
        self.side_combo.setVisible(show_side)
        # Populate the party's own accounts (— = none).
        self.party_bank_combo.blockSignals(True)
        self.party_bank_combo.clear()
        self.party_bank_combo.addItem("—", None)
        for bid, label in banks:
            self.party_bank_combo.addItem(label, bid)
        self.party_bank_combo.blockSignals(False)
        # Universal rule: negative = we must give, positive = we will receive.
        is_supplier = self.party_type == PARTY_BAPARI
        self.balance_label.setText(bal_text(is_supplier, bal))
        self.balance_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color:{bal_colour(is_supplier, bal)};"
        )
        # Show every load (newest first) so fully-paid trucks read 100%
        # and the boundary one shows its partial percentage.
        rows = list(reversed(loads))
        fill_table(
            self.out_table,
            [
                [str(o.txn_date), fmt(o.amount), fmt(o.paid),
                 fmt(o.outstanding), "", str(o.days)]
                for o in rows
            ],
        )
        for r, o in enumerate(rows):
            pct = float(o.paid / o.amount * 100) if o.amount > 0 else 100.0
            self.out_table.setCellWidget(r, 4, progress_cell(pct))
        self._apply_filter()

    def direction(self) -> str:
        """Which way this form says the money moved."""
        return self.dir_seg.current()

    def _on_direction_changed(self) -> None:
        out = self.direction() == PAYMENT_OUT
        self.dir_hint.setText(
            i18n.tr("dir_hint_out") if out else i18n.tr("dir_hint_in"))

    def _on_method_changed(self) -> None:
        # Every payment goes through an account now (cash -> a Cash account).
        if self.method_combo.currentData() == METHOD_CASH and self._cash_account_id:
            idx = self.account_combo.findData(self._cash_account_id)
            if idx >= 0:
                self.account_combo.setCurrentIndex(idx)

    def _on_account_changed(self) -> None:
        # Show how much money our selected account currently has.
        from timber.core import bank_service

        acc_id = self.account_combo.currentData()
        if not acc_id:
            self.account_avail_label.setText("")
            return
        # Read the batched balances loaded in refresh() — no round-trip per
        # selection (that per-account query was ~8 queries each time, which on
        # a cloud database made picking an account visibly lag).
        cached = getattr(self, "_acct_balances", None)
        if cached is not None and acc_id in cached:
            bal = cached[acc_id]
        else:
            with SessionLocal() as session:
                bal = bank_service.account_balance(session, acc_id)
        colour = "#c62828" if bal < 0 else "#1565c0"
        self.account_avail_label.setStyleSheet(f"color:{colour}; font-size:11px;")
        self.account_avail_label.setText(f"{i18n.tr('available')}: {bal:,.2f}")

    def _on_save(self) -> None:
        method = self.method_combo.currentData()
        account_id = self.account_combo.currentData()
        party_bank_id = self.party_bank_combo.currentData()
        if not self.party_combo.currentData():
            warn_toast(self, i18n.tr("cannot_save"), i18n.tr("select_party"))
            return
        if not account_id:
            warn_toast(
                self, i18n.tr("cannot_save"), i18n.tr("select_account_online")
            )
            return
        # The party's own account is optional on both sides.
        try:
            with SessionLocal() as session:
                payment = create_payment(
                    session,
                    txn_date=self.date_edit.date().toPython(),
                    party_id=self.party_combo.currentData(),
                    amount=self.amount_spin.value(),
                    method=method,
                    bank_account_id=account_id,
                    party_bank_id=party_bank_id,
                    reference_no=self.reference_edit.text().strip(),
                    notes=self.notes_edit.text().strip(),
                    split_side=(
                        self.side_combo.currentData()
                        if self.side_combo.isVisible() else None
                    ),
                    direction=self.direction(),
                    created_by=self.current_user.id,
                )
                # Strict rule: money LEAVING us can never overdraw an account.
                # Keyed off direction, not party type — a refund to a factory
                # spends real money, while a supplier returning cash cannot
                # overdraw anything.
                if self.direction() == PAYMENT_OUT:
                    from timber.core.bank_service import ensure_not_overdrawn
                    ensure_not_overdrawn(session, account_id)
                session.commit()
                summary = f"{i18n.tr('amount')}: {payment.amount:,.2f}"
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            err_toast(
                self, i18n.tr("error"), f"{i18n.tr('unexpected_error')}:\n{exc}"
            )
            return
        info_toast(self, i18n.tr("saved"), summary)
        self.amount_spin.setValue(0)
        self.reference_edit.clear()
        self.notes_edit.clear()
        dlg = getattr(self, "_record_dlg", None)
        if dlg is not None:
            dlg.accept()          # the box closes once the payment is in
        self.refresh()

    def _edit(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("edit"), i18n.tr("select_item"))
            return
        pid = self._ids[row]
        with SessionLocal() as session:
            payment = session.get(_Payment, pid)
            accounts = [
                (a.id, a.name) for a in session.scalars(
                    select(BankAccount).where(BankAccount.is_active.is_(True))
                    .order_by(BankAccount.name)
                )
            ]
            party = session.get(Party, payment.party_id)
            party_banks = [(b.id, party_bank_label(b)) for b in party.banks]
            data = dict(
                txn_date=payment.txn_date, amount=float(payment.amount),
                direction=payment.direction,
                method=payment.method, bank_account_id=payment.bank_account_id,
                party_bank_id=payment.party_bank_id,
                reference_no=payment.reference_no or "",
                notes=payment.notes or "",
            )
        dialog = _PaymentEditDialog(
            accounts, party_banks, data, self.party_type, parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        v = dialog.values()
        try:
            with SessionLocal() as session:
                update_payment(session, pid, created_by=self.current_user.id, **v)
                # Editing money OUT upward must not overdraw the account.
                if v.get("direction") == PAYMENT_OUT:
                    from timber.core.bank_service import ensure_not_overdrawn
                    ensure_not_overdrawn(session, v.get("bank_account_id"))
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _void(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("void"), i18n.tr("select_item"))
            return
        if not design.confirm(self, i18n.tr("void"), i18n.tr("confirm_delete"), danger=True):
            return
        try:
            with SessionLocal() as session:
                void_payment(session, self._ids[row], created_by=self.current_user.id)
                session.commit()
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()


class PaymentEntryScreen(QWidget):
    """Factory / Supplier / Unknown payment sections.

    The three panels are built ON DEMAND. Building all of them up front cost
    33 queries and ~370ms on every open, and most of that was for two sections
    the user had not looked at yet.
    """

    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        design.refresh()
        self.current_user = current_user

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        from timber.ui.screens.unknown_payment_panel import UnknownPaymentPanel

        specs = [
            ("factory", i18n.tr("factory"), "factory",
             lambda: PaymentPanel(current_user, PARTY_FACTORY)),
            ("bapari", i18n.tr("bapari"), "book-user",
             lambda: PaymentPanel(current_user, PARTY_BAPARI)),
            ("unknown", i18n.tr("unknown_tab"), "help-circle",
             lambda: UnknownPaymentPanel(current_user)),
        ]
        self._keys = [s[0] for s in specs]
        self._pending: dict[int, object] = {i: s[3] for i, s in enumerate(specs)}
        self._built: dict[int, QWidget] = {}

        self.segment = SegmentedControl([(s[0], s[1], s[2]) for s in specs])
        self.segment.changed.connect(self._on_segment)
        bar = QHBoxLayout()
        bar.addWidget(self.segment)
        bar.addStretch()
        root.addLayout(bar)

        self.stack = QStackedWidget()
        for _ in specs:
            host = QWidget()
            QVBoxLayout(host).setContentsMargins(0, 0, 0, 0)
            self.stack.addWidget(host)
        root.addWidget(self.stack, 1)

        self._ensure_tab(0)

    # -- lazy construction ---------------------------------------------
    def _on_segment(self, key: str) -> None:
        self._ensure_tab(self._keys.index(key))

    def _ensure_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        factory = self._pending.pop(index, None)
        if factory is None:
            return
        panel = factory()
        self.stack.widget(index).layout().addWidget(panel)
        self._built[index] = panel

    # Kept so existing callers (and tests) can still reach the panels.
    @property
    def factory_panel(self):
        return self._built.get(0)

    @property
    def bapari_panel(self):
        return self._built.get(1)

    @property
    def unknown_panel(self):
        return self._built.get(2)

    def refresh(self) -> None:
        for panel in self._built.values():
            panel.refresh()

    def live_refresh(self) -> None:
        # Only the visible section's records need the live update.
        panel = self._built.get(self.stack.currentIndex())
        if panel is not None and hasattr(panel, "live_refresh"):
            panel.live_refresh()
