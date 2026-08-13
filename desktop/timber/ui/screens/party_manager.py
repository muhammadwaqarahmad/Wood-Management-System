"""Manage parties — Factory and Bapari tabs, each with search + status
filter, account-title/IBAN columns, overdue highlight (factories), and
an editor for email, credit days, multiple phones, and multiple banks.
"""

from __future__ import annotations

import re
from decimal import Decimal

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QColor, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design
from timber.core import admin_service
from timber.core.current_user import CurrentUser
from timber.core.ledger import all_party_balances
from timber.core.permissions import Permission, Role, has_permission
from timber.core.reports import overdue_factory_ids
from timber.db.engine import SessionLocal
from timber.db.models import Location, Party
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.ui import icons, theme
from timber.ui.segmented import SegmentedControl
from timber.ui.screens.table_utils import (
    SearchBox,
    bal_colour,
    bal_text,
    colour_cell,
    fill_table,
    make_table,
    stacked_cell,
)

_P: dict = {}
_P_THEME: str | None = None


def _refresh_palette() -> None:
    global _P, _P_THEME
    _P = theme.palette()
    _P_THEME = theme.get_theme()


def _c(key: str) -> str:
    # Self-healing: a dialog can be built before (or after) the screen that
    # normally primes the palette. Without this, _P was empty and every colour
    # fell back to black — invisible on the dark theme.
    if not _P or _P_THEME != theme.get_theme():
        _refresh_palette()
    return _P.get(key, "#000000")


def _btn(kind: str = "ghost") -> str:
    """Theme-aware button styling shared by the master-data panels."""
    if kind == "primary":
        return (f"QPushButton{{background:{_c('accent')};color:#fff;border:none;"
                "border-radius:9px;padding:8px 18px;font-weight:800;}"
                "QPushButton:disabled{background:#94a3b8;color:#e2e8f0;}")
    if kind == "danger":
        return ("QPushButton{background:#e11d48;color:#fff;border:none;"
                "border-radius:9px;padding:8px 18px;font-weight:800;}"
                "QPushButton:hover{background:#be123c;}"
                "QPushButton:disabled{background:#94a3b8;color:#e2e8f0;}")
    return (f"QPushButton{{background:{_c('surface')};color:{_c('text')};"
            f"border:1px solid {_c('border')};border-radius:9px;padding:8px 16px;font-weight:700;}}"
            f"QPushButton:hover{{background:{_c('tab_bg')};}}"
            f"QPushButton:disabled{{color:{_c('muted')};}}")


def _input() -> str:
    return (f"QComboBox,QLineEdit{{background:{_c('input_bg')};border:1px solid {_c('input_border')};"
            f"border-radius:8px;padding:6px 10px;color:{_c('text')};min-height:20px;}}"
            f"QComboBox:focus,QLineEdit:focus{{border:1px solid {_c('accent')};}}"
            f"QComboBox QAbstractItemView{{background:{_c('input_bg')};color:{_c('text')};"
            f"selection-background-color:{_c('accent')};selection-color:#ffffff;}}")


class _BankCard(QFrame):
    """One compact bank-account row: index + 4 fields + remove."""

    def __init__(self, on_remove, data=None, parent=None) -> None:
        super().__init__(parent)
        _refresh_palette()
        self._on_remove = on_remove
        self.setFrameShape(QFrame.Shape.StyledPanel)
        # Four fields in one row needed ~850px and the column only has ~680,
        # so the card scrolled sideways and hid the account number. They wrap
        # 2x2 instead: nothing is cut off and no horizontal scrolling.
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        # Two 36px field rows + spacing + margins. Pinned so a crowded dialog
        # (a supplier also shows Linked factories) can never squash the card
        # and clip its second row of fields — the list scrolls instead.
        self.setMinimumHeight(106)

        self.index_label = QLabel("•")
        self.index_label.setFixedWidth(18)
        self.index_label.setStyleSheet("font-weight: bold;")
        lay.addWidget(self.index_label, alignment=Qt.AlignmentFlag.AlignTop)

        self.title_edit = QLineEdit(data.account_title if data and data.account_title else "")
        self.bank_edit = QLineEdit(data.bank_name if data and data.bank_name else "")
        self.iban_edit = QLineEdit(data.iban if data and data.iban else "")
        self.number_edit = QLineEdit(
            data.account_number if data and data.account_number else ""
        )
        self.title_edit.setPlaceholderText(i18n.tr("account_title"))
        self.bank_edit.setPlaceholderText(i18n.tr("bank_name"))
        self.iban_edit.setPlaceholderText(i18n.tr("iban"))
        self.iban_edit.setMaxLength(24)  # Pakistani IBAN length
        self.number_edit.setPlaceholderText(i18n.tr("account_number"))
        for e in (self.title_edit, self.bank_edit, self.iban_edit, self.number_edit):
            e.setMinimumHeight(36)      # match the rest of the app's inputs
            e.setMinimumWidth(120)      # small floor; the grid does the sizing

        fields = QGridLayout()
        fields.setHorizontalSpacing(10)
        fields.setVerticalSpacing(8)
        fields.setColumnStretch(0, 1)
        fields.setColumnStretch(1, 1)
        fields.addWidget(self.title_edit, 0, 0)
        fields.addWidget(self.bank_edit, 0, 1)
        fields.addWidget(self.iban_edit, 1, 0)
        fields.addWidget(self.number_edit, 1, 1)
        lay.addLayout(fields, 1)

        remove_btn = QPushButton(i18n.tr("remove"))
        remove_btn.setStyleSheet(design.btn("danger"))
        remove_btn.clicked.connect(lambda: self._on_remove(self))
        lay.addWidget(remove_btn, alignment=Qt.AlignmentFlag.AlignTop)

    def set_index(self, index: int) -> None:
        self.index_label.setText(str(index))

    def values(self) -> dict:
        return {
            "account_title": self.title_edit.text().strip(),
            "bank_name": self.bank_edit.text().strip(),
            "iban": self.iban_edit.text().strip(),
            "account_number": self.number_edit.text().strip(),
        }


class PartyDialog(design.Dialog):
    def __init__(
        self, locations, party=None, fixed_type=None, parent=None,
        can_edit_opening: bool = True,
    ) -> None:
        super().__init__(i18n.tr("edit") if party else i18n.tr("add"), "user",
                         party.name if party else "", parent=parent, width=980)
        # Ask for a roomy dialog but never exceed the screen; the body
        # scrolls, so a small laptop still reaches every field and Save.
        design.fit_to_screen(self, 1040, 840)
        _refresh_palette()      # this dialog can open before any screen does
        self._type = party.party_type if party else fixed_type
        self._bank_cards: list[_BankCard] = []
        self._can_edit_opening = can_edit_opening

        root = self.body

        # A single stacked column wasted the dialog's width and pushed the
        # phone/bank sections off the bottom. The details sit in TWO columns
        # with the caption above each input (the pattern used elsewhere in
        # the app), which halves the vertical space they need.
        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(14)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def _cell(row: int, col: int, label: str, widget) -> None:
            box = QVBoxLayout()
            box.setSpacing(6)
            cap = QLabel(label.upper())
            cap.setStyleSheet(
                f"color:{_c('muted')};font-size:11px;font-weight:700;"
                "letter-spacing:0.6px;"
            )
            widget.setMinimumHeight(38)
            box.addWidget(cap)
            box.addWidget(widget)
            grid.addLayout(box, row, col)

        # Bilingual name: the row shows in each user's own language.
        self.name_en_edit = QLineEdit(party.name_en if party and party.name_en else "")
        self.name_ur_edit = QLineEdit(party.name_ur if party and party.name_ur else "")
        self.email_edit = QLineEdit(party.email if party and party.email else "")
        self.address_edit = QLineEdit(party.address if party and party.address else "")

        self.location_combo = QComboBox()
        self.location_combo.addItem("—", None)
        for loc_id, loc_name in locations:
            self.location_combo.addItem(loc_name, loc_id)
        if party and party.location_id:
            self.location_combo.setCurrentIndex(
                self.location_combo.findData(party.location_id)
            )

        self.opening_spin = QDoubleSpinBox()
        self.opening_spin.setDecimals(2)
        self.opening_spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        self.opening_spin.setGroupSeparatorShown(True)
        if party:
            self.opening_spin.setValue(float(party.opening_balance))
        # The opening balance is the foundation of every balance after it —
        # only an Admin may set or change it.
        self.opening_spin.setEnabled(self._can_edit_opening)
        if not self._can_edit_opening:
            self.opening_spin.setToolTip(i18n.tr("opening_admin_only"))

        self.credit_spin = QSpinBox()
        self.credit_spin.setRange(0, 3650)
        if party and party.credit_days:
            self.credit_spin.setValue(party.credit_days)

        _cell(0, 0, i18n.tr("name_en"), self.name_en_edit)
        _cell(0, 1, i18n.tr("name_ur"), self.name_ur_edit)
        _cell(1, 0, i18n.tr("email"), self.email_edit)
        _cell(1, 1, i18n.tr("address"), self.address_edit)
        _cell(2, 0, i18n.tr("location"), self.location_combo)
        _cell(2, 1, i18n.tr("opening_balance"), self.opening_spin)
        if self._type == PARTY_FACTORY:
            _cell(3, 0, i18n.tr("credit_days"), self.credit_spin)
        root.addLayout(grid)

        # --- phones and banks sit SIDE BY SIDE ---------------------------
        # Stacked, the bank list was squeezed down to a single clipped row.
        # Phones need little width, banks need a lot, so they share one row.
        lower = QHBoxLayout()
        lower.setSpacing(22)

        phones_col = QVBoxLayout()
        phones_col.setSpacing(8)
        phones_col.addWidget(self._section_label(i18n.tr("phones")))
        phone_row = QHBoxLayout()
        phone_row.setSpacing(8)
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("03001234567")
        self.phone_input.setMaxLength(11)
        self.phone_input.setMinimumHeight(38)
        self.phone_input.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"\d{0,11}"))
        )
        self.phone_input.returnPressed.connect(self._add_phone)
        add_phone_btn = QPushButton(i18n.tr("add_phone"))
        add_phone_btn.setStyleSheet(_btn("ghost"))
        add_phone_btn.clicked.connect(self._add_phone)
        phone_row.addWidget(self.phone_input, 1)
        phone_row.addWidget(add_phone_btn)
        phones_col.addLayout(phone_row)

        self.phone_list = QListWidget()
        self.phone_list.setMinimumHeight(150)   # was a fixed 64px sliver
        if party:
            for p in party.phones:
                self.phone_list.addItem(p.phone)
        phones_col.addWidget(self.phone_list, 1)
        rm_phone_btn = QPushButton(i18n.tr("remove"))
        rm_phone_btn.setStyleSheet(_btn("ghost"))   # not a primary action
        rm_phone_btn.clicked.connect(self._remove_phone)
        phones_col.addWidget(rm_phone_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        banks_col = QVBoxLayout()
        banks_col.setSpacing(8)
        bank_head = QHBoxLayout()
        bank_head.addWidget(self._section_label(i18n.tr("banks")))
        bank_head.addStretch()
        add_bank_btn = QPushButton(i18n.tr("add_bank"))
        add_bank_btn.setStyleSheet(_btn("ghost"))
        add_bank_btn.clicked.connect(lambda: self._add_bank_card())
        bank_head.addWidget(add_bank_btn)
        banks_col.addLayout(bank_head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(230)        # room for ~2 wrapped accounts
        # Cards wrap now, so sideways scrolling would only ever mean something
        # is mis-sized — turn it off so nothing can hide off the right edge.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        self._banks_layout = QVBoxLayout(container)
        self._banks_layout.setSpacing(10)
        self._banks_layout.addStretch()
        scroll.setWidget(container)
        banks_col.addWidget(scroll, 1)
        lower.addLayout(banks_col, 5)

        root.addLayout(lower, 1)

        if party and party.banks:
            for b in party.banks:
                self._add_bank_card(b)
        else:
            self._add_bank_card()

        # Linked factories — which factories this SUPPLIER sells to. It only
        # applies to suppliers (a factory has no "linked factories" of its
        # own), and it now lives in the left column beneath the phones rather
        # than being tacked on under everything else, where it was pushed off
        # the bottom of the dialog.
        self.factory_list = None
        # Both sides of the SAME supplier<->factory link are editable now:
        # a supplier picks its factories, a factory picks its suppliers.
        self._link_is_factory_side = self._type == PARTY_FACTORY
        if self._type in (PARTY_BAPARI, PARTY_FACTORY):
            other_type = PARTY_BAPARI if self._link_is_factory_side else PARTY_FACTORY
            head_key = ("linked_suppliers" if self._link_is_factory_side
                        else "linked_factories")
            fhead = QHBoxLayout()
            fhead.addWidget(self._section_label(i18n.tr(head_key)))
            fhead.addStretch()
            self.factory_filter = QLineEdit()
            self.factory_filter.setPlaceholderText(i18n.tr("search"))
            self.factory_filter.setMinimumHeight(32)
            self.factory_filter.setMaximumWidth(150)
            fhead.addWidget(self.factory_filter)
            phones_col.addLayout(fhead)

            self.factory_list = QListWidget()
            self.factory_list.setMinimumHeight(200)
            if party is None:
                current_ids = set()
            elif self._link_is_factory_side:
                current_ids = {b.id for b in party.linked_baparis}
            else:
                current_ids = {f.id for f in party.linked_factories}
            with SessionLocal() as session:
                factories = [
                    (f.id, f.name) for f in session.scalars(
                        select(Party).where(
                            Party.party_type == other_type, Party.is_active.is_(True)
                        ).order_by(Party.name)
                    )
                ]
            for fid, fname in factories:
                item = QListWidgetItem(fname)
                item.setData(Qt.ItemDataRole.UserRole, fid)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.CheckState.Checked if fid in current_ids else Qt.CheckState.Unchecked
                )
                self.factory_list.addItem(item)
            # A supplier can deal with dozens of factories; let the user find
            # one instead of scrolling the whole checklist.
            self.factory_filter.textChanged.connect(self._filter_factories)
            phones_col.addWidget(self.factory_list, 1)

            fcount = QLabel("")
            fcount.setStyleSheet(f"color:{_c('muted')};font-size:11px;")
            self._factory_count_label = fcount
            phones_col.addWidget(fcount)
            self.factory_list.itemChanged.connect(self._update_factory_count)
            self._update_factory_count()

        lower.insertLayout(0, phones_col, 3)
        root.addLayout(lower, 1)

        ok, _cancel = self.buttons(i18n.tr("save"))
        ok.clicked.connect(self.accept)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        # Explicit palette colour: relying on inheritance meant the label took
        # whatever the parent happened to set, which is how these went
        # unreadable when the dialog background changed.
        lbl.setStyleSheet(
            f"color:{_c('text')};font-weight:800;font-size:13px;margin-top:6px;"
        )
        return lbl

    # -- phones --
    def _add_phone(self) -> None:
        text = self.phone_input.text().strip()
        if not text:
            return
        if not re.fullmatch(r"\d{11}", text):
            warn_toast(
                self, i18n.tr("cannot_save"), i18n.tr("phone_len_error")
            )
            return
        self.phone_list.addItem(text)
        self.phone_input.clear()
        self.phone_input.setFocus()

    def accept(self) -> None:
        # Enforce phone (11 digits) and IBAN (24 chars) lengths.
        for i in range(self.phone_list.count()):
            if not re.fullmatch(r"\d{11}", self.phone_list.item(i).text()):
                warn_toast(
                    self, i18n.tr("cannot_save"), i18n.tr("phone_len_error")
                )
                return
        for card in self._bank_cards:
            iban = card.iban_edit.text().strip()
            if iban and len(iban) != 24:
                warn_toast(
                    self, i18n.tr("cannot_save"), i18n.tr("iban_len_error")
                )
                return
        super().accept()

    def _remove_phone(self) -> None:
        row = self.phone_list.currentRow()
        if row >= 0:
            self.phone_list.takeItem(row)

    # -- banks --
    def _add_bank_card(self, data=None) -> None:
        card = _BankCard(self._remove_bank_card, data)
        self._bank_cards.append(card)
        # insert before the trailing stretch
        self._banks_layout.insertWidget(self._banks_layout.count() - 1, card)
        self._renumber_banks()

    def _remove_bank_card(self, card: _BankCard) -> None:
        if card in self._bank_cards:
            self._bank_cards.remove(card)
            self._banks_layout.removeWidget(card)
            card.deleteLater()
            self._renumber_banks()

    def _renumber_banks(self) -> None:
        for i, card in enumerate(self._bank_cards, 1):
            card.set_index(i)

    def _filter_factories(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for i in range(self.factory_list.count()):
            item = self.factory_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _update_factory_count(self, *_args) -> None:
        label = getattr(self, "_factory_count_label", None)
        if label is None or self.factory_list is None:
            return
        checked = sum(
            1 for i in range(self.factory_list.count())
            if self.factory_list.item(i).checkState() == Qt.CheckState.Checked
        )
        label.setText(f"{checked} / {self.factory_list.count()}")

    def values(self) -> dict:
        phones = [
            self.phone_list.item(i).text()
            for i in range(self.phone_list.count())
        ]
        banks = [card.values() for card in self._bank_cards]
        linked_factory_ids = None
        linked_bapari_ids = None
        if self.factory_list is not None:
            checked = [
                self.factory_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.factory_list.count())
                if self.factory_list.item(i).checkState() == Qt.CheckState.Checked
            ]
            if self._link_is_factory_side:
                linked_bapari_ids = checked
            else:
                linked_factory_ids = checked
        return dict(
            name_en=self.name_en_edit.text().strip(),
            name_ur=self.name_ur_edit.text().strip(),
            party_type=self._type,
            email=self.email_edit.text().strip(),
            address=self.address_edit.text().strip(),
            credit_days=(self.credit_spin.value() or None)
            if self._type == PARTY_FACTORY else None,
            location_id=self.location_combo.currentData(),
            opening_balance=self.opening_spin.value(),
            phones=phones,
            banks=banks,
            linked_factory_ids=linked_factory_ids,
            linked_bapari_ids=linked_bapari_ids,
        )


class PartyTypePanel(QWidget):
    def __init__(self, current_user: CurrentUser, party_type: str, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user
        self.party_type = party_type

        root = QVBoxLayout(self)

        filters = QHBoxLayout()
        balance_label = i18n.tr("balance")
        self.table = make_table(
            [
                i18n.tr("name"),
                i18n.tr("phone"),
                i18n.tr("location"),
                i18n.tr("address"),
                i18n.tr("banks"),
                balance_label,
                i18n.tr("status"),
            ]
        )
        self.table.setWordWrap(True)
        # Name stretches to fill leftover space; the rest are fixed so the
        # Bank accounts column stays a sensible (not huge) width.
        hdr = self.table.horizontalHeader()
        Fixed = QHeaderView.ResizeMode.Fixed
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name
        for col in (1, 2, 3, 4, 5, 6):
            hdr.setSectionResizeMode(col, Fixed)
        self.table.setColumnWidth(1, 150)   # Phone
        self.table.setColumnWidth(2, 110)   # Location
        self.table.setColumnWidth(3, 180)   # Address
        self.table.setColumnWidth(4, 340)   # Bank accounts
        self.table.setColumnWidth(5, 130)   # Balance
        self.table.setColumnWidth(6, 90)    # Status
        self.search = SearchBox(self.table)
        self.status_filter = QComboBox()
        self.status_filter.addItem(i18n.tr("all"), None)
        self.status_filter.addItem(i18n.tr("active"), True)
        self.status_filter.addItem(i18n.tr("inactive"), False)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.status_filter.setStyleSheet(_input())
        self.search.setStyleSheet(_input())
        filters.setSpacing(10)
        filters.addWidget(self.search, stretch=1)
        filters.addWidget(self.status_filter)
        root.setContentsMargins(0, 6, 0, 0)
        root.setSpacing(12)
        root.addLayout(filters)
        root.addWidget(self.table)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        # All party actions live in one tidy "Manage" dropdown (add / edit /
        # deactivate / delete), keeping the toolbar clean and consistent with
        # the rest of the app.
        self.manage_btn = design.manage_button([
            (i18n.tr("add"), self._add, "plus"),
            (i18n.tr("edit"), self._edit, "pencil"),
            (i18n.tr("deactivate"), self._toggle, "eye-off"),
            None,
            (i18n.tr("delete"), self._delete, "trash", "danger"),
        ], parent=self)
        buttons.addWidget(self.manage_btn)
        buttons.addStretch()
        root.addWidget(design.toolbar_wrap(buttons))

        # Per-action permissions: add/edit/deactivate need MANAGE_SETTINGS,
        # delete needs DELETE_RECORD.
        _acts = self.manage_btn._manage_actions  # [add, edit, deactivate, delete]
        if not has_permission(current_user.role, Permission.MANAGE_SETTINGS):
            for a in _acts[:3]:
                a.setEnabled(False)
        _acts[3].setEnabled(
            has_permission(current_user.role, Permission.DELETE_RECORD)
        )

        self.refresh()

    def _locations(self) -> list[tuple[int, str]]:
        with SessionLocal() as session:
            return [
                (loc.id, loc.name)
                for loc in session.scalars(
                    select(Location).where(Location.is_active.is_(True)).order_by(Location.name)
                )
            ]

    def refresh(self) -> None:
        status = self.status_filter.currentData()
        with SessionLocal() as session:
            # Eager-load phones/banks/location in a few bulk queries (not one
            # per party) and take every party's balance from ONE batched call.
            # This turned opening a data-heavy Master Data page from ~400
            # queries + a full ledger walk per party into a handful.
            query = (
                select(Party)
                .where(Party.party_type == self.party_type)
                .options(
                    selectinload(Party.phones),
                    selectinload(Party.banks),
                    joinedload(Party.location),
                )
            )
            if status is not None:
                query = query.where(Party.is_active.is_(status))
            parties = list(session.scalars(query.order_by(Party.name)).unique())
            self._ids = [p.id for p in parties]
            self._active = [p.is_active for p in parties]
            balances_map = all_party_balances(session)
            overdue = (
                overdue_factory_ids(session)
                if self.party_type == PARTY_FACTORY else set()
            )
            rows = []
            overdue_flags = []
            balances = []
            phone_cells = []
            bank_cells = []
            is_supplier = self.party_type == PARTY_BAPARI
            for p in parties:
                phone_items = [ph.phone for ph in p.phones]
                bank_items = []
                for b in p.banks:
                    head = " — ".join(x for x in (b.account_title, b.bank_name) if x)
                    sub = []
                    if b.iban:
                        sub.append(f"IBAN: {b.iban}")
                    if b.account_number:
                        sub.append(f"A/C: {b.account_number}")
                    text = "\n".join(part for part in [head, *sub] if part)
                    if text:
                        bank_items.append(text)
                phone_cells.append(phone_items)
                bank_cells.append(bank_items)
                balance = balances_map.get(p.id, Decimal("0.00"))
                rows.append(
                    [
                        p.name,
                        ", ".join(phone_items),   # col 1 (widget) — search text
                        p.location.name if p.location else "",
                        p.address or "",
                        " | ".join(bank_items),    # col 4 (widget) — search text
                        bal_text(is_supplier, balance),  # give = -, receive = +
                        i18n.tr("overdue") if p.id in overdue
                        else (i18n.tr("active") if p.is_active else i18n.tr("inactive")),
                    ]
                )
                overdue_flags.append(p.id in overdue)
                balances.append(balance)
        fill_table(self.table, rows)
        # Stack multiple phones (col 1) / banks (col 4) vertically with
        # divider lines. Clear the underlying text (the widget replaces it)
        # but keep the joined text as hidden search data for the filter.
        # A stacked cell widget is only needed when the cell really has several
        # entries (or one multi-line bank). Building two widgets for EVERY row
        # — plus a layout().activate() + adjustSize() on each — was what made
        # this page slow to open: ~190 widgets and layout passes for ~95
        # parties, while the queries themselves take only a few ms. Plain text
        # renders identically for the single-line case and costs nothing.
        for r, (phones, banks) in enumerate(zip(phone_cells, bank_cells)):
            needed = 36
            for col, items in ((1, phones), (4, banks)):
                item = self.table.item(r, col)
                item.setData(Qt.ItemDataRole.UserRole, item.text())  # search text
                multi = len(items) > 1 or (items and "\n" in items[0])
                if multi:
                    item.setText("")
                    w = stacked_cell(items)
                    self.table.setCellWidget(r, col, w)
                    # Activate so sizeHint reflects real content height,
                    # otherwise tall multi-account cells get clipped.
                    w.layout().activate()
                    w.adjustSize()
                    needed = max(needed, w.sizeHint().height())
                else:
                    self.table.setCellWidget(r, col, None)
                    item.setText(items[0] if items else "")
            self.table.setRowHeight(r, needed + 12)
        # Colour the balance (col 5): red = money WE must give (negative),
        # green = money we will receive (positive).
        for r, bal in enumerate(balances):
            colour_cell(self.table, r, 5, bal_colour(is_supplier, bal))
        # Highlight overdue rows in red.
        for r, is_overdue in enumerate(overdue_flags):
            if is_overdue:
                for c in range(self.table.columnCount()):
                    item = self.table.item(r, c)
                    if item:
                        item.setBackground(QColor("#ffe0e0"))
        self.search.apply()

    def _selected_row(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._ids):
            info_toast(self, i18n.tr("edit"), i18n.tr("select_item"))
            return None
        return row

    def _add(self) -> None:
        dialog = PartyDialog(
            self._locations(), fixed_type=self.party_type, parent=self,
            can_edit_opening=self.current_user.role == Role.ADMIN.value,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with SessionLocal() as session:
                admin_service.create_party(
                    session, created_by=self.current_user.id, **dialog.values()
                )
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _edit(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        party_id = self._ids[row]
        with SessionLocal() as session:
            party = session.get(Party, party_id)
            dialog = PartyDialog(
                self._locations(), party=party, parent=self,
                can_edit_opening=self.current_user.role == Role.ADMIN.value,
            )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        v = dialog.values()
        try:
            with SessionLocal() as session:
                admin_service.update_party(
                    session, party_id,
                    name_en=v["name_en"], name_ur=v["name_ur"],
                    email=v["email"], address=v["address"],
                    credit_days=v["credit_days"], update_credit_days=True,
                    location_id=v["location_id"], opening_balance=v["opening_balance"],
                    phones=v["phones"], banks=v["banks"],
                    linked_factory_ids=v["linked_factory_ids"],
                    created_by=self.current_user.id,
                )
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()

    def _toggle(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        try:
            with SessionLocal() as session:
                admin_service.set_party_active(
                    session, self._ids[row], not self._active[row],
                    created_by=self.current_user.id,
                )
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
        try:
            with SessionLocal() as session:
                admin_service.delete_party(
                    session, self._ids[row], created_by=self.current_user.id
                )
                session.commit()
                info_toast(self, i18n.tr("done_ok"), i18n.tr("done_ok"))
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        self.refresh()


class PartyManagerScreen(QWidget):
    """Master-data hub: Users, Factories, Suppliers and Wood types in tabs."""

    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        _refresh_palette()
        from timber.db.models import WoodType
        from timber.ui.screens.reference_manager import ReferenceManagerScreen
        from timber.ui.screens.user_manager import UserManagerScreen

        root = QVBoxLayout(self)
        # The page title already appears in the shared page bar — no duplicate.
        # Side inset so the tab bar + card sit off the panel's rounded edge,
        # consistent with the other pages.
        root.setContentsMargins(22, 8, 22, 14)
        root.setSpacing(0)

        # Panels are built ON FIRST VIEW. Building all four up front meant a
        # Master Data open paid for the users table, both party tables and the
        # wood-type table even though only one section is visible.
        specs = [
            ("users", i18n.tr("users"), "user",
             lambda: UserManagerScreen(current_user)),
            ("factory", i18n.tr("factory"), "factory",
             lambda: PartyTypePanel(current_user, PARTY_FACTORY)),
            ("bapari", i18n.tr("bapari"), "book-user",
             lambda: PartyTypePanel(current_user, PARTY_BAPARI)),
            ("wood", i18n.tr("wood_types"), "database",
             lambda: ReferenceManagerScreen(current_user, WoodType, "wood_types")),
        ]
        self._keys = [s[0] for s in specs]
        self._pending: dict[int, object] = {i: s[3] for i, s in enumerate(specs)}
        self._built: dict[int, QWidget] = {}

        self.segment = SegmentedControl([(s[0], s[1], s[2]) for s in specs])
        self.segment.changed.connect(self._on_segment)
        seg_row = QHBoxLayout()
        seg_row.setContentsMargins(0, 0, 0, 12)
        seg_row.addWidget(self.segment)
        seg_row.addStretch()
        root.addLayout(seg_row)

        # A card panel holds the active section.
        self.card = QFrame()
        self.card.setObjectName("mdCard")
        self.card.setStyleSheet(
            "#mdCard{background:" + _c("surface") + ";border:1px solid "
            + _c("border") + ";border-radius:16px;}")
        card_lay = QVBoxLayout(self.card)
        card_lay.setContentsMargins(16, 12, 16, 16)
        card_lay.setSpacing(0)
        self.stack = QStackedWidget()
        card_lay.addWidget(self.stack)
        for _ in specs:
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            self.stack.addWidget(page)
        root.addWidget(self.card, 1)

        self._ensure_tab(0)  # build the visible section now

    def _on_segment(self, key: str) -> None:
        index = self._keys.index(key)
        self._ensure_tab(index)
        self.stack.setCurrentIndex(index)

    def _ensure_tab(self, index: int) -> None:
        """Build a section's panel the first time it is shown."""
        self.stack.setCurrentIndex(index)
        factory = self._pending.pop(index, None)
        if factory is None:
            return
        panel = factory()
        self.stack.widget(index).layout().addWidget(panel)
        self._built[index] = panel

    # -- expose the panels the rest of the code expects -----------------
    @property
    def users_panel(self):
        return self._built.get(0)

    @property
    def factory_panel(self):
        return self._built.get(1)

    @property
    def bapari_panel(self):
        return self._built.get(2)

    @property
    def wood_panel(self):
        return self._built.get(3)

    def refresh(self) -> None:
        # Only refresh panels that have actually been built.
        for panel in self._built.values():
            if hasattr(panel, "refresh"):
                panel.refresh()
