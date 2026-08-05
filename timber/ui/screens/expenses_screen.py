"""Expenses — business vs house spending, with filters and statistics.

Two high-level buckets (tabs): Business and House, plus an All view.
Each view has period + category filters, stat cards and the table.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design
from timber.core import expense_service
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.db.engine import SessionLocal
from timber.db.models import BankAccount
from timber.db.models.expense import KIND_BUSINESS, KIND_HOUSE
from timber.ui.screens.table_utils import (
    SearchBox,
    attach_words,
    fill_table,
    fmt,
    make_table,
    words_label,
)


def _stat_card(accent: str, _unused: str = "") -> tuple[QFrame, QLabel, QLabel]:
    """A live-updating KPI tile; returns (frame, title_label, value_label).

    This page used to draw its own saturated gradient cards, which is why it
    never matched the Dashboard. It now uses the shared tile look — surface
    background, accent bar on the leading edge — while still handing back the
    two labels so ``refresh`` can keep writing into them.
    """
    design.refresh()
    box = QFrame()
    box.setObjectName("statCard")
    box.setStyleSheet(
        "#statCard{background:" + design.c("surface") + ";border:1px solid "
        + design.c("border") + ";border-radius:16px;border-left:4px solid "
        + accent + ";}")
    design.shadow(box, blur=20, dy=3)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(16, 13, 16, 14)
    lay.setSpacing(8)
    title = QLabel("")
    title.setWordWrap(True)
    title.setStyleSheet(
        f"color:{design.c('muted')};font-size:11px;font-weight:700;letter-spacing:0.6px;")
    value = QLabel("—")
    value.setStyleSheet(f"color:{design.c('text')};font-size:21px;font-weight:800;")
    lay.addWidget(title)
    lay.addWidget(value)
    return box, title, value


class ExpenseDialog(design.Dialog):
    def __init__(self, accounts, expense=None, parent=None, default_kind=None) -> None:
        super().__init__(i18n.tr("edit") if expense else i18n.tr("add"), "receipt", parent=parent, width=500)
        self.kind_combo = QComboBox()
        self.kind_combo.addItem(i18n.tr("business"), KIND_BUSINESS)
        self.kind_combo.addItem(i18n.tr("house"), KIND_HOUSE)
        want = expense.kind if expense else (default_kind or KIND_BUSINESS)
        idx = self.kind_combo.findData(want)
        if idx >= 0:
            self.kind_combo.setCurrentIndex(idx)
        self.field(i18n.tr("kind"), self.kind_combo)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        if expense:
            d = expense.txn_date
            self.date_edit.setDate(QDate(d.year, d.month, d.day))
        else:
            self.date_edit.setDate(QDate.currentDate())
        self.field(i18n.tr("date"), self.date_edit)

        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(expense_service.EXPENSE_CATEGORIES)
        self.category_combo.setCurrentIndex(-1)
        if expense:
            self.category_combo.setCurrentText(expense.category)
        self.field(i18n.tr("category"), self.category_combo)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setDecimals(2)
        self.amount_spin.setMaximum(1_000_000_000.0)
        self.amount_spin.setGroupSeparatorShown(True)
        if expense:
            self.amount_spin.setValue(float(expense.amount))
        self.field(i18n.tr("amount"), self.amount_spin)
        self.amount_words = words_label()
        attach_words(self.amount_spin, self.amount_words)
        self.add(self.amount_words)

        self.account_combo = QComboBox()
        self.account_combo.addItem("—", None)
        for acc_id, acc_name in accounts:
            self.account_combo.addItem(acc_name, acc_id)
        if expense and expense.bank_account_id:
            idx = self.account_combo.findData(expense.bank_account_id)
            if idx >= 0:
                self.account_combo.setCurrentIndex(idx)
        self.field(i18n.tr("bank_account"), self.account_combo)

        self.note_edit = QLineEdit(expense.note if expense and expense.note else "")
        self.field(i18n.tr("notes"), self.note_edit)

        ok, _cancel = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    def values(self) -> dict:
        return dict(
            txn_date=self.date_edit.date().toPython(),
            kind=self.kind_combo.currentData(),
            category=self.category_combo.currentText().strip(),
            amount=self.amount_spin.value(),
            bank_account_id=self.account_combo.currentData(),
            note=self.note_edit.text().strip(),
        )


class ExpensesScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user

        root = QVBoxLayout(self)

        # --- Filter row: kind tabs + period + category ------------------
        filters = QHBoxLayout()
        filters.setSpacing(8)

        self.kind_combo = QComboBox()
        self.kind_combo.addItem(i18n.tr("all"), None)
        self.kind_combo.addItem(i18n.tr("business"), KIND_BUSINESS)
        self.kind_combo.addItem(i18n.tr("house"), KIND_HOUSE)
        self.kind_combo.currentIndexChanged.connect(self.refresh)

        self.period_combo = QComboBox()
        for key, code in (
            ("all", "all"), ("day", "day"), ("month", "month"),
            ("year", "year"), ("custom", "custom"),
        ):
            self.period_combo.addItem(i18n.tr(key), code)
        # Opens on TODAY, like the other pages.
        self.period_combo.setCurrentIndex(self.period_combo.findData("day"))
        self.period_combo.currentIndexChanged.connect(self._period_changed)

        today = QDate.currentDate()
        self.from_edit = QDateEdit()
        self.from_edit.setCalendarPopup(True)
        self.from_edit.setDisplayFormat("yyyy-MM-dd")
        self.from_edit.setDate(today.addMonths(-1))
        self.to_edit = QDateEdit()
        self.to_edit.setCalendarPopup(True)
        self.to_edit.setDisplayFormat("yyyy-MM-dd")
        self.to_edit.setDate(today)
        self.from_edit.dateChanged.connect(self.refresh)
        self.to_edit.dateChanged.connect(self.refresh)
        self.from_edit.setVisible(False)
        self.to_edit.setVisible(False)

        self.category_filter = QComboBox()
        self.category_filter.addItem(i18n.tr("all"), None)
        for cat in expense_service.EXPENSE_CATEGORIES:
            self.category_filter.addItem(cat, cat)
        self.category_filter.currentIndexChanged.connect(self.refresh)

        filters.addWidget(QLabel(i18n.tr("kind")))
        filters.addWidget(self.kind_combo)
        filters.addWidget(QLabel(i18n.tr("period")))
        filters.addWidget(self.period_combo)
        filters.addWidget(self.from_edit)
        filters.addWidget(self.to_edit)
        filters.addWidget(QLabel(i18n.tr("category")))
        filters.addWidget(self.category_filter)
        self._filter_bar = filters
        root.addWidget(design.toolbar_wrap(filters))

        # --- Stat cards --------------------------------------------------
        cards = QHBoxLayout()
        cards.setSpacing(10)
        specs = [
            ("total_expenses", "#dc2626", "#b91c1c"),
            ("business_expenses", "#2563eb", "#1e40af"),
            ("house_expenses", "#d97706", "#b45309"),
            ("entries", "#475569", "#334155"),
            ("top_categories", "#7c3aed", "#5b21b6"),
        ]
        self._cards = {}
        for key, c1, c2 in specs:
            box, title, value = _stat_card(c1, c2)
            title.setText(i18n.tr(key).upper())
            cards.addWidget(box, 1)
            self._cards[key] = value
        root.addLayout(cards)

        self.table = make_table(
            [
                i18n.tr("date"),
                i18n.tr("kind"),
                i18n.tr("category"),
                i18n.tr("amount"),
                i18n.tr("bank_account"),
                i18n.tr("notes"),
            ]
        )
        # Search joins the filter row instead of sitting on its own line.
        self.search = SearchBox(self.table)
        self._filter_bar.addWidget(self.search, 1)
        root.addWidget(self.table)

        buttons = QHBoxLayout()
        self.add_btn = QPushButton(i18n.tr("add"))
        self.edit_btn = QPushButton(i18n.tr("edit"))
        self.void_btn = QPushButton(i18n.tr("void"))
        self.add_btn.clicked.connect(self._add)
        self.edit_btn.clicked.connect(self._edit)
        self.void_btn.clicked.connect(self._void)
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.edit_btn)
        buttons.addWidget(self.void_btn)
        buttons.addStretch()
        root.addWidget(design.toolbar_wrap(buttons))

        can = has_permission(current_user.role, Permission.MANAGE_PAYMENTS)
        self.add_btn.setEnabled(can)
        self.edit_btn.setEnabled(can)
        self.void_btn.setEnabled(can)

        self.refresh()

    # -- filters -------------------------------------------------------
    def _period_changed(self) -> None:
        custom = self.period_combo.currentData() == "custom"
        self.from_edit.setVisible(custom)
        self.to_edit.setVisible(custom)
        self.refresh()

    def _date_range(self) -> tuple[date | None, date | None]:
        code = self.period_combo.currentData()
        today = date.today()
        if code == "day":
            return today, today
        if code == "month":
            return today.replace(day=1), today
        if code == "year":
            return today.replace(month=1, day=1), today
        if code == "custom":
            return self.from_edit.date().toPython(), self.to_edit.date().toPython()
        return None, None

    def _accounts(self) -> list[tuple[int, str]]:
        with SessionLocal() as session:
            return [
                (a.id, a.name)
                for a in session.scalars(
                    select(BankAccount).where(BankAccount.is_active.is_(True)).order_by(BankAccount.name)
                )
            ]

    def refresh(self) -> None:
        kind = self.kind_combo.currentData() if hasattr(self, "kind_combo") else None
        category = self.category_filter.currentData() if hasattr(self, "category_filter") else None
        start, end = self._date_range()
        with SessionLocal() as session:
            rows = expense_service.list_expenses(
                session, kind=kind, category=category, start=start, end=end
            )
            stats = expense_service.expense_stats(
                session, kind=kind, start=start, end=end
            )
        self._ids = [r.id for r in rows]
        kind_names = {KIND_BUSINESS: i18n.tr("business"), KIND_HOUSE: i18n.tr("house")}
        fill_table(
            self.table,
            [
                [str(r.txn_date), kind_names.get(r.kind, r.kind), r.category,
                 fmt(r.amount), r.account_name, r.note]
                for r in rows
            ],
        )
        self.search.apply()
        self._cards["total_expenses"].setText(fmt(stats.total))
        self._cards["business_expenses"].setText(fmt(stats.business))
        self._cards["house_expenses"].setText(fmt(stats.house))
        self._cards["entries"].setText(str(stats.count))
        top = " · ".join(f"{c} {fmt(a)}" for c, a in stats.by_category[:2]) or "—"
        self._cards["top_categories"].setText(top)

    # -- CRUD ------------------------------------------------------------
    def _add(self) -> None:
        dialog = ExpenseDialog(
            self._accounts(), parent=self,
            default_kind=self.kind_combo.currentData() or KIND_BUSINESS,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        v = dialog.values()
        try:
            with SessionLocal() as session:
                expense_service.create_expense(
                    session, created_by=self.current_user.id, **v
                )
                # Strict rule: an expense can't overdraw the account.
                from timber.core import bank_service
                bank_service.ensure_not_overdrawn(session, v.get("bank_account_id"))
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _edit(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("edit"), i18n.tr("select_item"))
            return
        from timber.db.models import Expense
        with SessionLocal() as session:
            expense = session.get(Expense, self._ids[row])
            dialog = ExpenseDialog(self._accounts(), expense=expense, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with SessionLocal() as session:
                v = dialog.values()
                expense_service.update_expense(
                    session, self._ids[row], created_by=self.current_user.id, **v
                )
                # Same strict rule as creating one: editing an expense UP must
                # not overdraw the account. Without this a small expense could
                # be saved past the guard and then raised to any amount.
                from timber.core import bank_service
                bank_service.ensure_not_overdrawn(session, v.get("bank_account_id"))
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _void(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("void"), i18n.tr("select_item"))
            return
        try:
            with SessionLocal() as session:
                expense_service.void_expense(
                    session, self._ids[row], created_by=self.current_user.id
                )
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()
