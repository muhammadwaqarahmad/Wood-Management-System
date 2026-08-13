"""Buy & Sell (trade) entry — the primary entry screen.

A truck can carry several wood types, each with its own muds/kg and its
own bapari (buy) and factory (sell) rate. One bapari and one factory per
truck; loading/freight/unloading are entered once for the whole truck.
Each wood line is saved as its own buy+sell load, grouped as one trade.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.ui import design, icons
from timber.core.calculations import compute_bill, sale_weight, to_decimal
from timber.core.current_user import CurrentUser
from timber.core.ledger import party_balance
from timber.core.lookups import (
    last_rate_for_party,
    linked_factory_ids,
    recent_vehicles,
)
from timber.core.num_to_words import to_words
from timber.core.permissions import Permission, has_permission
from timber.core.transaction_service import WoodLine, create_mixed_trade
from timber.db.engine import SessionLocal
from timber.db.models import Party, WoodType
from timber.db.models.combined_txn import PAYER_BAPARI, PAYER_FACTORY, PAYER_US
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.ui.screens.table_utils import bal_colour, bal_text

_MAX = 1_000_000_000.0


def _pair(label1: str, w1, label2: str, w2) -> QHBoxLayout:
    row = QHBoxLayout()
    l1 = QLabel(label1)
    l1.setMinimumWidth(90)
    row.addWidget(l1)
    row.addWidget(w1, 1)
    row.addSpacing(24)
    l2 = QLabel(label2)
    l2.setMinimumWidth(90)
    row.addWidget(l2)
    row.addWidget(w2, 1)
    return row


def _spin(decimals: int) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setMaximum(_MAX)
    spin.setGroupSeparatorShown(True)
    return spin


# Column widths. Wood type keeps a normal width; the weight/rate boxes are
# comfortably sized. Any spare space sits on the far right.
# Sized so a full wood line fits inside a ~960px dialog instead of the ~1120
# it used to need (which forced the edit dialog to be enormous).
_WOOD_W = 184   # wood type box
_FAC_W = 168    # factory weight box (spin + kg button)
_SUP_W = 132    # supplier weight box (whole maunds)
_RATE_W = 112   # rate boxes
_DIV_GAP = 14   # gap on each side of the factory | supplier divider


def _card(title: str | None = None):
    """A white rounded 'card' panel with a soft shadow and an optional title.
    Returns (frame, inner_vbox) so callers can add content."""
    frame = QFrame()
    frame.setObjectName("bsCard")
    v = QVBoxLayout(frame)
    v.setContentsMargins(18, 16, 18, 16)
    v.setSpacing(12)
    if title:
        t = QLabel(title)
        t.setObjectName("bsCardTitle")
        v.addWidget(t)
    shadow = QGraphicsDropShadowEffect(frame)
    shadow.setBlurRadius(18)
    shadow.setColor(QColor(15, 23, 42, 28))
    shadow.setOffset(0, 2)
    frame.setGraphicsEffect(shadow)
    return frame, v


def _labeled(text: str, widget, extra=None) -> QVBoxLayout:
    """A small uppercase caption above a field, with an optional chip below."""
    box = QVBoxLayout()
    box.setSpacing(6)
    lbl = QLabel(text.upper())
    lbl.setObjectName("bsFieldLabel")
    box.addWidget(lbl)
    box.addWidget(widget)
    if extra is not None:
        box.addWidget(extra, alignment=Qt.AlignmentFlag.AlignLeft)
    return box


def _stat(title: str):
    """One stat in the dark totals bar: caption + value label (returned)."""
    box = QVBoxLayout()
    box.setSpacing(2)
    t = QLabel(title.upper())
    t.setObjectName("barStatTitle")
    v = QLabel("0.00")
    v.setObjectName("barStatValue")
    box.addWidget(t)
    box.addWidget(v)
    return box, v


_BS_STYLE = """
#bsScroll, #bsContent { background: #f1f5f9; }
QLabel#bsHeader { font-size: 21px; font-weight: bold; color: #0f172a; }
QFrame#bsCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 14px; }
QLabel#bsCardTitle { font-size: 14px; font-weight: bold; color: #0f172a; }
QLabel#bsFieldLabel { font-size: 11px; font-weight: 600; color: #64748b; }
QLabel#bsHint { color: #64748b; font-size: 11px; }
QFrame#totalsBar { background: #0f172a; border-radius: 14px; }
QLabel#barStatTitle { color: #94a3b8; font-size: 10px; font-weight: 600; }
QLabel#barStatValue { color: #e2e8f0; font-size: 15px; font-weight: 600; }
QLabel#barProfitTitle { color: #94a3b8; font-size: 10px; font-weight: 600; }
QPushButton#bsSave {
    background: #4f46e5; color: white; border: none; border-radius: 10px;
    padding: 10px 26px; font-weight: bold;
}
QPushButton#bsSave:hover { background: #4338ca; }
QPushButton#bsSave:disabled { background: #64748b; color: #cbd5e1; }
"""


def _vline() -> QFrame:
    """A plain, solid, full-height vertical divider between the factory and
    supplier sides."""
    line = QFrame()
    line.setFixedWidth(2)
    line.setStyleSheet("background:#475569; border:none;")
    line.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
    return line


class ExpenseInput(QWidget):
    """One loading / freight / unloading expense entered per truck.

    The supplier ALWAYS bears the cost — this widget only captures *who
    paid the driver* (who fronted the cash):
      • We paid   → cash leaves our account, then deducted from supplier.
      • Factory   → factory returns us less, then deducted from supplier.
      • Supplier  → paid the driver directly; nothing recorded for us.
    Tick "Split" when two parties shared the front (e.g. half us, half
    factory); the first amount goes to payer 1, the rest to payer 2.
    """

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self.amount_spin = _spin(2)
        self.amount_spin.setFixedWidth(160)  # a normal, compact amount box
        row.addWidget(self.amount_spin)

        row.addWidget(QLabel(i18n.tr("paid_by")))
        self.payer_combo = _driver_payer_combo()
        row.addWidget(self.payer_combo)

        self.split_check = QPushButton(i18n.tr("split_toggle"))
        self.split_check.setCheckable(True)
        self.split_check.setFixedWidth(70)
        row.addWidget(self.split_check)

        # The split half: "first [amount] then rest by [payer2]".
        self.split_box = QWidget()
        sb = QHBoxLayout(self.split_box)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(6)
        sb.addWidget(QLabel(i18n.tr("split_first")))
        self.split_spin = _spin(2)
        self.split_spin.setFixedWidth(110)
        self.split_spin.setToolTip(i18n.tr("split_amount_hint"))
        sb.addWidget(self.split_spin)
        sb.addWidget(QLabel(i18n.tr("split_rest")))
        self.payer2_combo = _driver_payer_combo()
        sb.addWidget(self.payer2_combo)
        row.addWidget(self.split_box)
        self.split_box.setVisible(False)
        row.addStretch()  # keep the controls compact on the left

        self.split_check.toggled.connect(self.split_box.setVisible)
        self.split_check.toggled.connect(lambda _: self.changed.emit())
        self.amount_spin.valueChanged.connect(lambda _: self.changed.emit())
        self.split_spin.valueChanged.connect(lambda _: self.changed.emit())
        self.payer_combo.currentIndexChanged.connect(lambda _: self.changed.emit())
        self.payer2_combo.currentIndexChanged.connect(lambda _: self.changed.emit())

    # -- read --
    def amount(self) -> float:
        return self.amount_spin.value()

    def payer(self):
        return self.payer_combo.currentData()

    def payer2(self):
        return self.payer2_combo.currentData() if self.split_check.isChecked() else None

    def split(self) -> float:
        return self.split_spin.value() if self.split_check.isChecked() else 0.0

    # -- write (edit mode) --
    def set_values(self, amount, payer, payer2=None, split=0) -> None:
        self.amount_spin.setValue(float(amount or 0))
        idx = self.payer_combo.findData(payer)
        if idx >= 0:
            self.payer_combo.setCurrentIndex(idx)
        if payer2:
            self.split_check.setChecked(True)
            i2 = self.payer2_combo.findData(payer2)
            if i2 >= 0:
                self.payer2_combo.setCurrentIndex(i2)
            self.split_spin.setValue(float(split or 0))

    def reset(self) -> None:
        self.amount_spin.setValue(0)
        self.split_spin.setValue(0)
        self.split_check.setChecked(False)
        self.payer_combo.setCurrentIndex(0)
        self.payer2_combo.setCurrentIndex(0)


def _driver_payer_combo() -> QComboBox:
    """Who paid the driver: us (business), factory, or supplier directly."""
    combo = QComboBox()
    combo.addItem(i18n.tr("paid_we"), PAYER_US)
    combo.addItem(i18n.tr("paid_factory"), PAYER_FACTORY)
    combo.addItem(i18n.tr("paid_supplier"), PAYER_BAPARI)
    return combo


class _WeightCell(QWidget):
    """A single weight box in DECIMAL maunds, e.g. 432.32. A small "kg" button
    opens a popup to type the weight in kilograms, which is converted to maunds
    (kg / 40) and filled in. Weight is stored as decimal maunds (kg folded in)."""

    def __init__(self, on_change, show_kg: bool = True, whole: bool = False) -> None:
        super().__init__()
        self._on_change = on_change
        self._whole = whole  # supplier weight is counted in whole maunds only
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.spin = _spin(0 if whole else 2)
        self.spin.setToolTip(i18n.tr("weight_muds_hint"))
        lay.addWidget(self.spin, 1)
        if show_kg:
            self.kg_btn = QPushButton(i18n.tr("in_kg"))
            self.kg_btn.setFixedWidth(42)
            self.kg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # Override the app's roomy button padding so "kg" isn't clipped.
            self.kg_btn.setStyleSheet(
                "QPushButton { background:#2563eb; color:white; border:none;"
                " border-radius:6px; padding:4px 6px; font-weight:700; }"
                "QPushButton:hover { background:#1d4ed8; }"
            )
            self.kg_btn.setToolTip(i18n.tr("enter_kg_hint"))
            self.kg_btn.clicked.connect(self._enter_kg)
            lay.addWidget(self.kg_btn)

        self.spin.valueChanged.connect(lambda _: self._on_change())

    def _enter_kg(self) -> None:
        # The same Kg calculator Buy & Sell uses — this used to be a bare
        # QInputDialog, so the two screens asked for kg in different ways.
        # Imported lazily to keep the module import graph one-directional.
        from timber.ui.screens.buy_sell_screen import _KgDialog

        dlg = _KgDialog(self)
        dlg.set_mode("weight")
        if dlg.exec():
            self.set_value(to_decimal(dlg.result_value))

    def value(self) -> float:
        return self.spin.value()

    def muds_kg(self):
        """(maunds, kg) for storage — kg is folded into the maunds value."""
        return self.spin.value(), 0

    def is_zero(self) -> bool:
        return self.spin.value() == 0

    def copy_to(self, other: "_WeightCell") -> None:
        other.set_value(self.spin.value())

    def set_value(self, muds) -> None:
        v = float(muds)
        if self._whole:
            v = float(int(v))  # drop the decimal point (truncate) for supplier
        self.spin.setValue(v)

    def set_from_muds_kg(self, muds, kg) -> None:
        self.set_value(to_decimal(muds) + to_decimal(kg) / 40)


class _WoodLineRow(QWidget):
    """One wood line: wood type + the FACTORY weight/rate first (the factory
    slip is recorded first), then the SUPPLIER weight/rate. Entering the factory
    weight auto-fills the supplier weight, which stays editable."""

    def __init__(self, wood_types, on_change, on_remove) -> None:
        super().__init__()
        self._on_remove = on_remove
        self._on_change = on_change
        self._copying = False
        # Hug the content. The factory|supplier divider inside this row has an
        # Expanding vertical policy, so without a Fixed policy here the row
        # absorbed all the dialog's spare height — leaving a tall empty band
        # between the column titles and the input boxes.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(6)

        self.wood_combo = QComboBox()
        self.wood_combo.addItem("—", None)
        # Entries are (id, name) or (id, name, supplier_rate, factory_rate).
        # The 2-tuple form is still used by the Trade History edit dialog.
        self._wood_rates: dict[int, tuple[float, float]] = {}
        for entry in wood_types:
            wid, wname = entry[0], entry[1]
            self.wood_combo.addItem(wname, wid)
            if len(entry) >= 4:
                self._wood_rates[wid] = (float(entry[2] or 0), float(entry[3] or 0))
        # True while set_values() is loading a SAVED trade, so the wood's
        # defaults never overwrite the rates that trade was actually done at.
        self._loading = False
        # Factory side first (decimal, with the kg button). Supplier side is
        # counted in WHOLE maunds only (no decimal point).
        self.fac_cell = _WeightCell(self._fac_changed, show_kg=True)
        self.factory_rate_spin = _spin(2)
        self.sup_cell = _WeightCell(self._sup_changed, show_kg=False, whole=True)
        self.bapari_rate_spin = _spin(2)
        self.wood_combo.setFixedWidth(_WOOD_W)
        self.fac_cell.setFixedWidth(_FAC_W)
        self.factory_rate_spin.setFixedWidth(_RATE_W)
        self.sup_cell.setFixedWidth(_SUP_W)
        self.bapari_rate_spin.setFixedWidth(_RATE_W)

        lay.addWidget(self.wood_combo)
        lay.addWidget(self.fac_cell)
        lay.addWidget(self.factory_rate_spin)
        lay.addSpacing(_DIV_GAP)
        lay.addWidget(_vline())             # divider: factory side | supplier side
        lay.addSpacing(_DIV_GAP)
        lay.addWidget(self.sup_cell)
        lay.addWidget(self.bapari_rate_spin)
        lay.addSpacing(24)                  # small gap before Remove

        # Icon-only: the word "Remove" cost ~55px on every wood line and the
        # trash icon says the same thing.
        self.remove_btn = QPushButton()
        self.remove_btn.setIcon(icons.icon("trash", design.c("muted"), 15))
        self.remove_btn.setToolTip(i18n.tr("remove"))
        self.remove_btn.setFixedWidth(38)
        self.remove_btn.clicked.connect(lambda: self._on_remove(self))
        lay.addWidget(self.remove_btn)
        lay.addStretch(1)                   # any spare space goes to the far right

        # currentIndexChanged/valueChanged carry a value; ``changed`` takes
        # none. Connecting them straight through pushed that value into
        # changed.emit() and raised "changed() only accepts 0 argument(s)"
        # every time a saved trade was loaded for editing. Swallow the arg.
        self.wood_combo.currentIndexChanged.connect(
            lambda *_: self._apply_wood_defaults())
        self.wood_combo.currentIndexChanged.connect(lambda *_: on_change())
        self.bapari_rate_spin.valueChanged.connect(lambda *_: on_change())
        self.factory_rate_spin.valueChanged.connect(lambda *_: on_change())

    def _apply_wood_defaults(self) -> None:
        """Pre-fill both rates from the chosen wood's defaults.

        Only fills a side whose default is set (greater than zero), and never
        while a saved trade is being loaded. The spins stay fully editable —
        this is a starting point, not a locked price.
        """
        if self._loading:
            return
        wid = self.wood_combo.currentData()
        rates = self._wood_rates.get(wid)
        if not rates:
            return
        sup_rate, fac_rate = rates
        if sup_rate > 0:
            self.bapari_rate_spin.setValue(sup_rate)
        if fac_rate > 0:
            self.factory_rate_spin.setValue(fac_rate)

    def _fac_changed(self) -> None:
        # Factory weight always drives the supplier weight (carrying decimals).
        # Changing the supplier alone never changes the factory weight.
        self._copying = True
        self.fac_cell.copy_to(self.sup_cell)
        self._copying = False
        self._on_change()

    def _sup_changed(self) -> None:
        self._on_change()

    def values(self) -> WoodLine:
        s_muds, s_kg = self.sup_cell.muds_kg()
        f_muds, f_kg = self.fac_cell.muds_kg()
        return WoodLine(
            wood_type_id=self.wood_combo.currentData(),
            muds=s_muds, kg=s_kg,
            bapari_rate=self.bapari_rate_spin.value(),
            factory_rate=self.factory_rate_spin.value(),
            factory_muds=f_muds, factory_kg=f_kg,
        )

    def is_empty(self) -> bool:
        return self.fac_cell.is_zero() and self.sup_cell.is_zero()

    def set_values(self, wood_id, muds, kg, b_rate, f_rate,
                   f_muds=None, f_kg=None) -> None:
        # Guard the wood-change handler: a saved trade keeps ITS rates.
        self._loading = True
        try:
            idx = self.wood_combo.findData(wood_id)
            self.wood_combo.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self._loading = False
        self.bapari_rate_spin.setValue(float(b_rate))
        self.factory_rate_spin.setValue(float(f_rate))
        # Set the factory weight first (auto-copies to supplier), then set the
        # supplier's own stored weight.
        if f_muds is not None or f_kg is not None:
            self.fac_cell.set_from_muds_kg(
                f_muds if f_muds is not None else muds,
                f_kg if f_kg is not None else kg,
            )
        else:
            self.fac_cell.set_from_muds_kg(muds, kg)
        self.sup_cell.set_from_muds_kg(muds, kg)


class WoodLinesWidget(QWidget):
    """A growable list of wood lines (factory side first) with a header and an
    Add button. Weight is entered in decimal maunds; a per-box "kg" button
    converts a kilogram figure when the factory slip is in kg."""

    changed = Signal()

    def __init__(self, wood_types, parent=None) -> None:
        super().__init__(parent)
        self._wood_types = wood_types
        self.rows: list[_WoodLineRow] = []
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        header.setContentsMargins(0, 0, 0, 2)

        def _hlabel(text, width=None, stretch=0):
            lbl = QLabel(text)
            lbl.setStyleSheet(
                "font-weight:700;font-size:11px;letter-spacing:0.5px;"
                f"color:{design.c('muted')};")
            lbl.setFixedHeight(18)
            if width:
                lbl.setFixedWidth(width)
            header.addWidget(lbl, stretch)

        _hlabel(i18n.tr("wood_type"), _WOOD_W)
        _hlabel(i18n.tr("factory_weight"), _FAC_W)
        _hlabel(f"{i18n.tr('factory')} {i18n.tr('rate')}", _RATE_W)
        header.addSpacing(_DIV_GAP)
        # A SHORT divider here. _vline() expands vertically, which in a header
        # row stretched the whole strip and left a tall empty band above and
        # below the column titles.
        head_div = _vline()
        head_div.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        head_div.setFixedHeight(18)
        header.addWidget(head_div)
        header.addSpacing(_DIV_GAP)
        _hlabel(i18n.tr("supplier_weight"), _SUP_W)
        _hlabel(f"{i18n.tr('supplier')} {i18n.tr('rate')}", _RATE_W)
        header.addStretch(1)
        root.addLayout(header)

        self._rows_box = QVBoxLayout()
        self._rows_box.setSpacing(4)
        root.addLayout(self._rows_box)

        self.add_btn = QPushButton(i18n.tr("add_wood"))
        self.add_btn.clicked.connect(lambda: self.add_row())
        root.addWidget(self.add_btn, alignment=Qt.AlignmentFlag.AlignLeft)

    def set_wood_types(self, wood_types) -> None:
        self._wood_types = wood_types

    def add_row(self, wood_id=None, muds=0, kg=0, b_rate=0, f_rate=0,
                f_muds=None, f_kg=None) -> _WoodLineRow:
        row = _WoodLineRow(self._wood_types, self.changed.emit, self._remove)
        if wood_id or muds or kg or b_rate or f_rate or f_muds or f_kg:
            row.set_values(wood_id, muds, kg, b_rate, f_rate, f_muds, f_kg)
        self.rows.append(row)
        self._rows_box.addWidget(row)
        self._update_remove_state()
        self.changed.emit()
        return row

    def _remove(self, row: _WoodLineRow) -> None:
        if len(self.rows) <= 1:
            return  # always keep at least one line
        self.rows.remove(row)
        self._rows_box.removeWidget(row)
        row.deleteLater()
        self._update_remove_state()
        self.changed.emit()

    def _update_remove_state(self) -> None:
        only_one = len(self.rows) <= 1
        for r in self.rows:
            r.remove_btn.setEnabled(not only_one)

    def lines(self) -> list[WoodLine]:
        return [r.values() for r in self.rows]

    def reset(self) -> None:
        for r in list(self.rows):
            self._rows_box.removeWidget(r)
            r.deleteLater()
        self.rows.clear()
        self.add_row()


class TradeEntryScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.current_user = current_user

        self.setStyleSheet(_BS_STYLE)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Everything scrolls except the totals bar, which stays pinned.
        scroll = QScrollArea()
        scroll.setObjectName("bsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("bsContent")
        body = QVBoxLayout(content)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(16)

        header = QLabel(i18n.tr("trade"))
        header.setObjectName("bsHeader")
        body.addWidget(header)

        # --- Card: trade details ---
        details_card, dc = _card()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.vehicle_edit = QLineEdit()
        self.vehicle_edit.setPlaceholderText("LEA-1234")
        from timber.ui.searchable import SearchableComboBox

        self.bapari_combo = SearchableComboBox(i18n.tr("search"))
        self.bapari_combo.currentIndexChanged.connect(self._on_bapari_changed)
        self.bapari_balance_label = QLabel("")
        self.factory_combo = SearchableComboBox(i18n.tr("search"))
        self.factory_combo.currentIndexChanged.connect(self._on_factory_changed)
        self.factory_balance_label = QLabel("")

        details = QHBoxLayout()
        details.setSpacing(18)
        details.addLayout(_labeled(i18n.tr("date"), self.date_edit), 1)
        details.addLayout(_labeled(i18n.tr("vehicle_no"), self.vehicle_edit), 1)
        details.addLayout(
            _labeled(i18n.tr("bapari"), self.bapari_combo, self.bapari_balance_label), 1)
        details.addLayout(
            _labeled(i18n.tr("factory"), self.factory_combo, self.factory_balance_label), 1)
        dc.addLayout(details)
        body.addWidget(details_card)

        # --- Card: wood lines ---
        wood_card, wc = _card(i18n.tr("wood_lines"))
        self.lines_widget = WoodLinesWidget([])
        self.lines_widget.changed.connect(self._recalculate)
        wc.addWidget(self.lines_widget)
        body.addWidget(wood_card)

        # --- Card: loading / freight / unloading ---
        exp_card, ec = _card(i18n.tr("charges_title"))
        hint = QLabel(i18n.tr("charges_hint"))
        hint.setObjectName("bsHint")
        ec.addWidget(hint)
        exp_form = QFormLayout()
        exp_form.setHorizontalSpacing(14)
        self.loading_exp = ExpenseInput()
        exp_form.addRow(i18n.tr("loading"), self.loading_exp)
        self.freight_exp = ExpenseInput()
        exp_form.addRow(i18n.tr("freight"), self.freight_exp)
        self.unloading_exp = ExpenseInput()
        exp_form.addRow(i18n.tr("unloading"), self.unloading_exp)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setFixedHeight(44)
        exp_form.addRow(i18n.tr("notes"), self.notes_edit)
        ec.addLayout(exp_form)
        body.addWidget(exp_card)

        body.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # --- Totals bar (pinned, dark) ---
        bar = QFrame()
        bar.setObjectName("totalsBar")
        barlay = QHBoxLayout(bar)
        barlay.setContentsMargins(20, 14, 20, 14)
        barlay.setSpacing(26)
        b1, self.purchase_val = _stat(i18n.tr("purchase_bill"))
        b2, self.sale_val = _stat(i18n.tr("sale_bill"))
        b3, self.freight_val = _stat(i18n.tr("freight"))
        b4, self.supplier_val = _stat(i18n.tr("supplier_net"))
        b5, self.factory_val = _stat(i18n.tr("factory_net"))
        for b in (b1, b2, b3, b4, b5):
            barlay.addLayout(b)
        barlay.addStretch()
        pbox = QVBoxLayout()
        pbox.setSpacing(2)
        ptitle = QLabel(i18n.tr("profit").upper())
        ptitle.setObjectName("barProfitTitle")
        self.profit_val = QLabel("0.00")
        pbox.addWidget(ptitle)
        pbox.addWidget(self.profit_val)
        barlay.addLayout(pbox)
        barlay.addSpacing(18)
        self.save_btn = QPushButton(i18n.tr("save"))
        self.save_btn.setObjectName("bsSave")
        self.save_btn.clicked.connect(self._on_save)
        barlay.addWidget(self.save_btn)
        root.addWidget(bar)

        for exp in (self.loading_exp, self.freight_exp, self.unloading_exp):
            exp.changed.connect(self._recalculate)

        if not has_permission(current_user.role, Permission.CREATE_TXN):
            self.save_btn.setEnabled(False)
            self.save_btn.setText(i18n.tr("no_permission"))

        self.refresh()
        self._recalculate()

    def _charges(self) -> dict[str, Decimal]:
        charges = {PAYER_US: Decimal("0"), PAYER_BAPARI: Decimal("0"),
                   PAYER_FACTORY: Decimal("0")}
        for exp in (self.loading_exp, self.freight_exp, self.unloading_exp):
            amt = to_decimal(exp.amount())
            p1 = exp.payer()
            p2 = exp.payer2()
            if p2:
                primary = min(to_decimal(exp.split()), amt)
                charges[p1] += primary
                charges[p2] += amt - primary
            else:
                charges[p1] += amt
        return charges

    # -- data ---------------------------------------------------------
    def refresh(self) -> None:
        with SessionLocal() as session:
            baparis = session.scalars(
                select(Party).where(Party.party_type == PARTY_BAPARI,
                                    Party.is_active.is_(True)).order_by(Party.name)
            ).all()
            factories = session.scalars(
                select(Party).where(Party.party_type == PARTY_FACTORY,
                                    Party.is_active.is_(True)).order_by(Party.name)
            ).all()
            woods = session.scalars(
                select(WoodType).where(WoodType.is_active.is_(True)).order_by(WoodType.name)
            ).all()
            vehicles = recent_vehicles(session)

        self._all_factories = [(p.id, p.name) for p in factories]
        self._wood_types = [
            (w.id, w.name, w.default_supplier_rate, w.default_factory_rate)
            for w in woods
        ]

        self.bapari_combo.blockSignals(True)
        self.bapari_combo.clear()
        for p in baparis:
            self.bapari_combo.addItem(p.name, p.id)
        self.bapari_combo.setCurrentIndex(-1)
        self.bapari_combo.blockSignals(False)
        self._populate_factories(self._all_factories)

        self.lines_widget.set_wood_types(self._wood_types)
        if not self.lines_widget.rows:
            self.lines_widget.add_row()

        completer = QCompleter(vehicles, self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.vehicle_edit.setCompleter(completer)
        from timber.ui.searchable import style_completer_popup
        style_completer_popup(completer)

    def _populate_factories(self, items) -> None:
        self.factory_combo.blockSignals(True)
        self.factory_combo.clear()
        for fid, fname in items:
            self.factory_combo.addItem(fname, fid)
        self.factory_combo.setCurrentIndex(-1)
        self.factory_combo.blockSignals(False)

    def _update_balance(self, party_id, label, is_supplier) -> None:
        if not party_id:
            label.setText("")
            label.setStyleSheet("")
            return
        with SessionLocal() as session:
            bal = party_balance(session, party_id)
        # Universal rule: negative = we must give, positive = we will receive.
        # Shown as a coloured pill (green = receive, red = give).
        colour = bal_colour(is_supplier, bal)
        bg = {"#16a34a": "#dcfce7", "#c62828": "#fee2e2"}.get(colour, "#f1f5f9")
        label.setText(bal_text(is_supplier, bal))
        label.setStyleSheet(
            f"background:{bg}; color:{colour}; padding:2px 8px;"
            " border-radius:6px; font-weight:600; font-size:12px;"
        )

    def _on_bapari_changed(self) -> None:
        pid = self.bapari_combo.currentData()
        self._update_balance(pid, self.bapari_balance_label, is_supplier=True)
        if not pid:
            self._populate_factories(self._all_factories)
            return
        with SessionLocal() as session:
            rate = last_rate_for_party(session, pid, PARTY_BAPARI)
            linked = set(linked_factory_ids(session, pid))
        if rate is not None and self.lines_widget.rows:
            first = self.lines_widget.rows[0]
            if first.bapari_rate_spin.value() == 0:
                first.bapari_rate_spin.setValue(float(rate))
        items = [(fid, fn) for fid, fn in self._all_factories if fid in linked]
        self._populate_factories(items or self._all_factories)

    def _on_factory_changed(self) -> None:
        pid = self.factory_combo.currentData()
        self._update_balance(pid, self.factory_balance_label, is_supplier=False)
        if not pid:
            return
        with SessionLocal() as session:
            rate = last_rate_for_party(session, pid, PARTY_FACTORY)
        if rate is not None and self.lines_widget.rows:
            first = self.lines_widget.rows[0]
            if first.factory_rate_spin.value() == 0:
                first.factory_rate_spin.setValue(float(rate))

    # -- behaviour ----------------------------------------------------
    def _totals(self):
        # Profit is the gross margin (sale - purchase). Freight is a pass-
        # through borne by the supplier, so it never affects profit.
        charges = self._charges()  # how much each side fronted to the driver
        purchase = Decimal("0")
        sale = Decimal("0")
        for ln in self.lines_widget.lines():
            purchase += compute_bill(sale_weight(ln.muds, ln.kg), ln.bapari_rate)
            f_muds = ln.factory_muds if ln.factory_muds not in (None, "") else ln.muds
            f_kg = ln.factory_kg if ln.factory_kg not in (None, "") else ln.kg
            sale += compute_bill(sale_weight(f_muds, f_kg), ln.factory_rate)
        total_freight = (
            to_decimal(self.loading_exp.amount())
            + to_decimal(self.freight_exp.amount())
            + to_decimal(self.unloading_exp.amount())
        )
        profit = sale - purchase
        # Supplier always bears the part fronted by factory/us; factory's
        # receivable drops by what the factory fronted.
        supplier_net = purchase - (charges[PAYER_FACTORY] + charges[PAYER_US])
        factory_net = sale - charges[PAYER_FACTORY]
        return purchase, sale, profit, total_freight, supplier_net, factory_net

    def _recalculate(self) -> None:
        purchase, sale, profit, total_freight, sup_net, fac_net = self._totals()
        self.purchase_val.setText(f"{purchase:,.2f}")
        self.sale_val.setText(f"{sale:,.2f}")
        self.freight_val.setText(f"{total_freight:,.2f}")
        self.supplier_val.setText(f"{sup_net:,.2f}")
        self.factory_val.setText(f"{fac_net:,.2f}")
        colour = "#4ade80" if profit >= 0 else "#f87171"  # green / red on dark
        self.profit_val.setStyleSheet(
            f"color:{colour}; font-size:22px; font-weight:bold;"
        )
        self.profit_val.setText(f"{profit:,.2f}")

    def _on_save(self) -> None:
        bapari_id = self.bapari_combo.currentData()
        factory_id = self.factory_combo.currentData()
        txn_date = self.date_edit.date().toPython()
        try:
            with SessionLocal() as session:
                created = create_mixed_trade(
                    session,
                    txn_date=txn_date,
                    bapari_id=bapari_id,
                    factory_id=factory_id,
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
                    notes=self.notes_edit.toPlainText().strip(),
                    created_by=self.current_user.id,
                )
                session.commit()
                total_profit = sum((c.profit for c in created), Decimal("0"))
                summary = (
                    f"{len(created)} {i18n.tr('wood_lines')} — "
                    f"{i18n.tr('profit')} {total_profit:,.2f}"
                )
        except ValueError as exc:
            warn_toast(self, i18n.tr("cannot_save"), str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            err_toast(
                self, i18n.tr("error"), f"{i18n.tr('unexpected_error')}:\n{exc}"
            )
            return

        info_toast(self, i18n.tr("saved"), summary)
        self._reset_inputs()
        self._update_balance(bapari_id, self.bapari_balance_label, is_supplier=True)
        self._update_balance(factory_id, self.factory_balance_label, is_supplier=False)

    def _reset_inputs(self) -> None:
        for exp in (self.loading_exp, self.freight_exp, self.unloading_exp):
            exp.reset()
        self.vehicle_edit.clear()
        self.notes_edit.clear()
        self.lines_widget.reset()
        self._recalculate()
