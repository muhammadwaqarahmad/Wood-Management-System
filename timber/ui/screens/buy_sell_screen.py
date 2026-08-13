"""Buy & Sell — native, theme-aware rebuild faithful to the former React page.

Sections: General Details, Wood Inventory Details, Logistics Costs, and a pinned
dark totals bar. All colours come from the active theme palette (light/dark) and
every label is an i18n key, so the page follows the app theme AND translates.
Saving calls the unchanged ``create_mixed_trade`` — identical numbers to before.
"""

from __future__ import annotations

import math
from decimal import Decimal

from sqlalchemy import select

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from timber import config, i18n
from timber.ui import design
from timber.core.current_user import CurrentUser
from timber.core.permissions import Permission, has_permission
from timber.core.transaction_service import WoodLine, create_mixed_trade
from timber.db.engine import SessionLocal
from timber.db.models import Party, WoodType
from timber.db.models.combined_txn import PAYER_BAPARI, PAYER_FACTORY, PAYER_US
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.ui import icons, theme
from timber.ui.searchable import SearchableComboBox
from timber.ui.toast import err_toast, info_toast, warn_toast

# wood-line column widths (px), shared by the header and each row
W_FAC_W, W_FAC_R, W_KG, W_SUP_W, W_SUP_R, W_DEL = 130, 120, 50, 130, 120, 36
W_WOOD_MAX = 300

# --- active theme palette (refreshed each time the screen is built) ----------
_P: dict = {}
_P_THEME: str | None = None
_POS = "#059669"
_NEG = "#e11d48"
_ZERO = "#64748b"


def _refresh_palette() -> None:
    global _P, _P_THEME, _POS, _NEG, _ZERO
    _P = theme.palette()
    _P_THEME = theme.get_theme()
    dark = theme.get_theme() == "dark"
    _POS = "#34d399" if dark else "#059669"
    _NEG = "#fb7185" if dark else "#e11d48"
    _ZERO = _P.get("muted", "#64748b")


def _c(key: str) -> str:
    # Self-healing: a widget can be built before the palette is primed (or
    # after a theme switch). Without this every colour fell back to black,
    # which is invisible on the dark theme.
    if not _P or _P_THEME != theme.get_theme():
        _refresh_palette()
    return _P.get(key, "#000000")


def _t(key: str) -> str:
    r = i18n.tr(key)
    return r if r else key


def _money(v) -> str:
    return f"{float(v):,.2f}"


def _amt_color(v: float) -> str:
    return _POS if v > 0 else _NEG if v < 0 else _ZERO


def _input_style() -> str:
    return (
        f"QDoubleSpinBox,QLineEdit,QComboBox,QDateEdit{{background:{_c('input_bg')};"
        f"border:1px solid {_c('input_border')};border-radius:8px;padding:6px 8px;"
        f"color:{_c('text')};}}"
        f"QDoubleSpinBox:focus,QLineEdit:focus,QComboBox:focus,QDateEdit:focus{{border:1px solid {_c('accent')};}}"
        f"QComboBox QAbstractItemView{{background:{_c('input_bg')};color:{_c('text')};"
        f"selection-background-color:{_c('accent')};selection-color:#ffffff;}}"
    )


def _spin(step=0.01, whole=False) -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    sp.setDecimals(0 if whole else 2)
    sp.setMaximum(1e12)
    sp.setSingleStep(step)
    sp.setAlignment(Qt.AlignmentFlag.AlignRight)
    sp.setStyleSheet(_input_style())
    return sp


def _payer_combo() -> QComboBox:
    c = QComboBox()
    c.setStyleSheet(_input_style())
    c.addItem(config.APP_NAME, PAYER_US)     # "Abdul Sattar Woods"
    c.addItem(_t("factory"), PAYER_FACTORY)
    c.addItem(_t("bapari"), PAYER_BAPARI)
    return c


class _KgDialog(design.Dialog):
    """Kg calculator: Weight (kg/40 = maunds) or Rate (rate/kg * 40 = /maund)."""

    def __init__(self, parent=None):
        super().__init__(_t("kg_calculator"), "cart", parent=parent, width=380)
        # Dialog height is normally derived from the width; this one has only
        # four short controls, so that left a large empty band. Tighten the
        # body and let it size to what is actually in it.
        self.body.setSpacing(9)
        self.body.setContentsMargins(20, 14, 20, 8)
        self.mode = "weight"
        self.result_value = 0.0
        # The design header already shows the title, so no second one here.
        lay = self.body

        seg = QFrame()
        seg.setStyleSheet("QFrame{background:" + _c("tab_bg") + ";border-radius:10px;}")
        sgl = QHBoxLayout(seg); sgl.setContentsMargins(4, 4, 4, 4); sgl.setSpacing(4)
        self.b_weight = QPushButton(_t("weight"))
        self.b_rate = QPushButton(_t("rate"))
        for b in (self.b_weight, self.b_rate):
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            sgl.addWidget(b, 1)
        self.b_weight.setChecked(True)
        self.b_weight.clicked.connect(lambda: self._set_mode("weight"))
        self.b_rate.clicked.connect(lambda: self._set_mode("rate"))
        lay.addWidget(seg)

        self.caption = QLabel(_t("weight_in_kg"))
        self.caption.setStyleSheet(f"color:{_c('muted')};font-size:11px;font-weight:700;letter-spacing:0.4px;")
        lay.addWidget(self.caption)
        self.inp = _spin()
        self.inp.setMinimumHeight(42)
        self.inp.setStyleSheet(_input_style() + "QDoubleSpinBox{font-size:18px;}")
        self.inp.valueChanged.connect(self._preview)
        lay.addWidget(self.inp)

        self.preview = QLabel("= 0.00")
        self.preview.setStyleSheet(
            f"background:{_c('tab_bg')};color:{_c('accent')};border-radius:10px;"
            "padding:10px 12px;font-size:15px;font-weight:800;")
        lay.addWidget(self.preview)

        btns = QHBoxLayout(); btns.addStretch()
        cancel = QPushButton(_t("cancel"))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setStyleSheet(
            f"QPushButton{{background:{_c('tab_bg')};color:{_c('text')};border:none;"
            "border-radius:8px;padding:8px 16px;font-weight:700;}")
        cancel.clicked.connect(self.reject)
        apply = QPushButton(_t("apply"))
        apply.setCursor(Qt.CursorShape.PointingHandCursor)
        apply.setStyleSheet(
            f"QPushButton{{background:{_c('accent')};color:#fff;border:none;"
            "border-radius:8px;padding:8px 20px;font-weight:800;}")
        apply.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(apply)
        lay.addLayout(btns)
        self._style_toggle()
        self._preview()
        # Shrink to the content instead of keeping the width-derived height.
        self.adjustSize()
        self.setFixedHeight(min(self.sizeHint().height(), 420))

    def set_mode(self, m: str) -> None:
        """Public entry point so other screens can preselect a mode."""
        self._set_mode(m)

    def _set_mode(self, m):
        self.mode = m
        self.inp.setValue(0)
        self.caption.setText(_t("weight_in_kg") if m == "weight" else _t("rate_per_kg"))
        self._style_toggle()
        self._preview()

    def _style_toggle(self):
        for b, m in ((self.b_weight, "weight"), (self.b_rate, "rate")):
            on = self.mode == m
            b.setStyleSheet(
                "QPushButton{border:none;border-radius:8px;padding:7px 14px;font-weight:700;"
                + (f"background:{_c('accent')};color:#fff;" if on
                   else f"background:transparent;color:{_c('muted')};") + "}")

    def _preview(self):
        v = self.inp.value()
        self.result_value = v / 40 if self.mode == "weight" else v * 40
        unit = _t("maunds") if self.mode == "weight" else _t("per_maund")
        self.preview.setText(f"= {_money(self.result_value)}  {unit}")


class _WoodRow(QWidget):
    changed = Signal()
    removed = Signal(object)

    def __init__(self, wood_types):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.wood = SearchableComboBox(_t("search"))
        self.wood.setStyleSheet(_input_style())
        self.wood.setMaximumWidth(W_WOOD_MAX)
        # {wood_id: (supplier_rate, factory_rate)} so picking a wood can
        # pre-fill both sides. Entries are (id, name, sup_rate, fac_rate);
        # shorter tuples simply carry no defaults.
        self._wood_rates: dict[int, tuple[float, float]] = {}
        for entry in wood_types:
            wid, wname = entry[0], entry[1]
            sup_rate = entry[2] if len(entry) > 2 else 0.0
            fac_rate = entry[3] if len(entry) > 3 else 0.0
            self.wood.addItem(wname, wid)
            if sup_rate or fac_rate:
                self._wood_rates[wid] = (float(sup_rate or 0), float(fac_rate or 0))
        self.wood.setCurrentIndex(-1)
        self.wood.currentIndexChanged.connect(self._apply_default_rate)
        lay.addWidget(self.wood, 1)

        self.fac_w = _spin(); self.fac_w.setFixedWidth(W_FAC_W)
        self.fac_r = _spin(); self.fac_r.setFixedWidth(W_FAC_R)
        lay.addWidget(self.fac_w)
        lay.addWidget(self.fac_r)
        lay.addWidget(self._divider())

        self.kg_btn = QPushButton(_t("kg")); self.kg_btn.setFixedWidth(W_KG)
        self.kg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.kg_btn.setStyleSheet(
            f"QPushButton{{background:{_c('accent')};color:#fff;border:none;border-radius:8px;padding:6px 0;font-weight:800;}}")
        self.kg_btn.clicked.connect(self._open_kg)
        lay.addWidget(self.kg_btn)
        lay.addWidget(self._divider())

        self.sup_w = _spin(step=1, whole=True); self.sup_w.setFixedWidth(W_SUP_W)
        self.sup_r = _spin(); self.sup_r.setFixedWidth(W_SUP_R)
        lay.addWidget(self.sup_w)
        lay.addWidget(self.sup_r)

        self.del_btn = QPushButton(); self.del_btn.setFixedWidth(W_DEL)
        try:
            self.del_btn.setIcon(icons.icon("x", _c("muted"), 15))
        except Exception:  # noqa: BLE001
            self.del_btn.setText("x")
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.setStyleSheet("QPushButton{background:transparent;border:none;}")
        self.del_btn.clicked.connect(lambda: self.removed.emit(self))
        lay.addWidget(self.del_btn)
        lay.addStretch(1)

        self.fac_w.valueChanged.connect(self._sync_sup_weight)
        for sp in (self.fac_w, self.fac_r, self.sup_w, self.sup_r):
            sp.valueChanged.connect(lambda _=0: self.changed.emit())

    def _apply_default_rate(self) -> None:
        """Pre-fill BOTH rates from the chosen wood: what we pay the supplier
        and what we charge the factory.

        Only fills a rate that is still 0, so it never overwrites something
        already typed, and both spins stay fully editable afterwards — the
        wood's rates are a starting point, not a fixed price.
        """
        rates = self._wood_rates.get(self.wood.currentData())
        if not rates:
            return
        sup_rate, fac_rate = rates
        # The signal can fire before these spins exist.
        sup = getattr(self, "sup_r", None)
        fac = getattr(self, "fac_r", None)
        if sup is not None and sup_rate > 0 and not sup.value():
            sup.setValue(sup_rate)
        if fac is not None and fac_rate > 0 and not fac.value():
            fac.setValue(fac_rate)

    def _divider(self):
        d = QFrame(); d.setFixedWidth(1); d.setStyleSheet(f"background:{_c('border')};")
        return d

    def _sync_sup_weight(self, v):
        self.sup_w.blockSignals(True)
        self.sup_w.setValue(math.trunc(v))
        self.sup_w.blockSignals(False)
        self.changed.emit()

    def _open_kg(self):
        dlg = _KgDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.mode == "weight":
                self.fac_w.setValue(dlg.result_value)
            else:
                self.fac_r.setValue(dlg.result_value)

    def wood_line(self) -> WoodLine:
        return WoodLine(
            wood_type_id=self.wood.currentData(),
            muds=self.sup_w.value(), kg=0,
            bapari_rate=self.sup_r.value(),
            factory_rate=self.fac_r.value(),
            factory_muds=self.fac_w.value(), factory_kg=0,
        )


class _ChargeRow(QWidget):
    changed = Signal()

    def __init__(self, label):
        super().__init__()
        self.setObjectName("chg")
        self.setStyleSheet(
            "#chg{background:" + _c("alt_row") + ";border:1px solid " + _c("border") + ";border-radius:12px;}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)
        cap = QLabel(label); cap.setFixedWidth(90)
        cap.setStyleSheet(f"color:{_c('text')};font-weight:600;background:transparent;border:none;")
        lay.addWidget(cap)
        self.amount = _spin(); self.amount.setFixedWidth(140)
        lay.addWidget(self.amount)
        pb = QLabel(_t("paid_by")); pb.setStyleSheet(f"color:{_c('muted')};font-size:12px;background:transparent;border:none;")
        lay.addWidget(pb)
        self.payer = _payer_combo()
        self.payer.setCurrentIndex(1)  # default Factory
        lay.addWidget(self.payer)
        self.split_btn = QPushButton(_t("split_toggle")); self.split_btn.setCheckable(True)
        self.split_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.split_btn)

        self.split_box = QWidget()
        sb = QHBoxLayout(self.split_box); sb.setContentsMargins(0, 0, 0, 0); sb.setSpacing(6)
        first = QLabel(_t("split_first")); first.setStyleSheet(f"color:{_c('muted')};background:transparent;border:none;")
        sb.addWidget(first)
        self.split_amt = _spin(); self.split_amt.setFixedWidth(110)
        sb.addWidget(self.split_amt)
        rest = QLabel(_t("split_rest")); rest.setStyleSheet(f"color:{_c('muted')};background:transparent;border:none;")
        sb.addWidget(rest)
        self.payer2 = _payer_combo()
        self.payer2.setCurrentIndex(0)
        sb.addWidget(self.payer2)
        lay.addWidget(self.split_box)
        self.split_box.setVisible(False)
        lay.addStretch()

        self.split_btn.toggled.connect(self.split_box.setVisible)
        self.split_btn.toggled.connect(lambda _: (self._style_split(), self.changed.emit()))
        self.amount.valueChanged.connect(lambda _: self.changed.emit())
        self.split_amt.valueChanged.connect(lambda _: self.changed.emit())
        self.payer.currentIndexChanged.connect(lambda _: self.changed.emit())
        self.payer2.currentIndexChanged.connect(lambda _: self.changed.emit())
        self._style_split()

    def _style_split(self):
        on = self.split_btn.isChecked()
        self.split_btn.setStyleSheet(
            "QPushButton{border-radius:8px;padding:6px 12px;font-weight:700;"
            + (f"background:{_c('accent')};color:#fff;border:none;" if on
               else f"background:{_c('surface')};color:{_c('muted')};border:1px solid {_c('border')};") + "}")

    def values(self):
        amt = self.amount.value()
        if self.split_btn.isChecked() and 0 < self.split_amt.value() < amt:
            return amt, self.payer.currentData(), self.payer2.currentData(), self.split_amt.value()
        return amt, self.payer.currentData(), None, 0

    def reset(self):
        self.amount.setValue(0)
        self.split_amt.setValue(0)
        self.split_btn.setChecked(False)
        self.payer.setCurrentIndex(1)
        self.payer2.setCurrentIndex(0)


class BuySellScreen(QWidget):
    no_live_refresh = False

    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        _refresh_palette()  # colours for the ACTIVE theme (light/dark)
        self.current_user = current_user
        self._rows: list[_WoodRow] = []
        self._wood_types: list[tuple] = []
        self._balances: dict = {}   # party_id -> balance, batched in refresh()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;} QScrollArea > QWidget > QWidget{background:transparent;}")
        body = QWidget()
        outer_h = QHBoxLayout(body)
        outer_h.setContentsMargins(16, 6, 16, 8)
        outer_h.setSpacing(0)
        outer_h.addStretch(1)
        center = QWidget()
        center.setMaximumWidth(1180)
        self.v = QVBoxLayout(center)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.v.setSpacing(16)
        outer_h.addWidget(center, 30)
        outer_h.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # --- General Details ---
        details = design.Card(_t("general_details"), "calendar-clock")
        grid = QHBoxLayout(); grid.setSpacing(16)
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setStyleSheet(_input_style())
        self.vehicle = QLineEdit(); self.vehicle.setPlaceholderText("LEA-1234")
        self.vehicle.setStyleSheet(_input_style())
        self.supplier = SearchableComboBox(_t("search"))
        self.factory = SearchableComboBox(_t("search"))
        self.supplier.setStyleSheet(_input_style())
        self.factory.setStyleSheet(_input_style())
        self.sup_bal = QLabel(""); self.fac_bal = QLabel("")
        self.supplier.currentIndexChanged.connect(lambda _: self._on_party(True))
        self.factory.currentIndexChanged.connect(lambda _: self._on_party(False))
        grid.addLayout(self._field(_t("date"), self.date_edit), 1)
        grid.addLayout(self._field(_t("vehicle_no"), self.vehicle), 1)
        grid.addLayout(self._field(_t("bapari"), self.supplier, self.sup_bal), 1)
        grid.addLayout(self._field(_t("factory"), self.factory, self.fac_bal), 1)
        details.addL(grid)
        self.v.addWidget(details)

        # --- Wood Inventory Details ---
        self.wood_card = design.Card(_t("wood_inventory"), "receipt")
        header = QHBoxLayout(); header.setContentsMargins(0, 0, 0, 0); header.setSpacing(8)

        def hcol(text, width, stretch=0):
            lbl = QLabel(text.upper())
            lbl.setStyleSheet(f"color:{_c('muted')};font-size:11px;font-weight:700;letter-spacing:0.5px;")
            if width:
                lbl.setFixedWidth(width)
            if stretch:
                lbl.setMaximumWidth(W_WOOD_MAX)
            header.addWidget(lbl, stretch)

        hcol(_t("wood_type"), 0, 1)
        hcol(_t("factory_weight"), W_FAC_W)
        hcol(_t("factory_rate"), W_FAC_R)
        hcol("", 1)
        hcol(_t("kg"), W_KG)
        hcol("", 1)
        hcol(_t("supplier_weight"), W_SUP_W)
        hcol(_t("supplier_rate"), W_SUP_R)
        hcol("", W_DEL)
        header.addStretch(1)
        hw = QWidget(); hw.setLayout(header)
        self.wood_card.add(hw)
        self._rows_box = QVBoxLayout(); self._rows_box.setSpacing(6)
        rows_wrap = QWidget(); rows_wrap.setLayout(self._rows_box)
        self.wood_card.add(rows_wrap)
        # The "add_wood" string already carries its own leading "+".
        add_btn = QPushButton(_t("add_wood"))
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            f"QPushButton{{background:{_c('sidebar_bg')};color:#fff;border:none;border-radius:8px;padding:8px 16px;font-weight:700;}}")
        add_btn.clicked.connect(lambda: self._add_row())
        wrap = QHBoxLayout(); wrap.addWidget(add_btn); wrap.addStretch()
        self.wood_card.addL(wrap)
        self.v.addWidget(self.wood_card)

        # --- Logistics Costs ---
        charges = design.Card(_t("logistics_costs"), "wallet")
        self.loading = _ChargeRow(_t("loading"))
        self.freight = _ChargeRow(_t("freight"))
        self.unloading = _ChargeRow(_t("unloading"))
        for c in (self.loading, self.freight, self.unloading):
            c.changed.connect(self._recalc)
            charges.add(c)
        self.v.addWidget(charges)

        self.banner = QLabel("")
        self.banner.setVisible(False)
        self.banner.setWordWrap(True)
        self.v.addWidget(self.banner)
        self.v.addStretch()

        # --- pinned totals bar (always dark, like the sidebar) ---
        bar = QFrame(); bar.setObjectName("bar"); bar.setMaximumWidth(1180)
        bar.setStyleSheet("#bar{background:" + _c("sidebar_bg") + ";border-radius:14px;}")
        bl = QHBoxLayout(bar); bl.setContentsMargins(20, 14, 20, 14); bl.setSpacing(26)
        self.t_purchase = self._stat(bl, _t("purchase_bill"))
        self.t_sale = self._stat(bl, _t("sale_bill"))
        self.t_freight = self._stat(bl, _t("freight"), muted=True)
        self.t_supnet = self._stat(bl, _t("supplier_net"), muted=True)
        self.t_facnet = self._stat(bl, _t("factory_net"), muted=True)
        bl.addStretch()
        pb = QVBoxLayout(); pb.setSpacing(2)
        pt = QLabel(_t("profit").upper()); pt.setStyleSheet("color:#94a3b8;font-size:10px;font-weight:700;letter-spacing:1px;")
        self.t_profit = QLabel("0.00")
        pb.addWidget(pt); pb.addWidget(self.t_profit)
        bl.addLayout(pb)
        bl.addSpacing(16)
        self.save_btn = QPushButton(_t("save_trade"))
        try:
            self.save_btn.setIcon(icons.icon("file-check", "#ffffff", 18))
        except Exception:  # noqa: BLE001
            pass
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(
            f"QPushButton{{background:{_c('accent')};color:#fff;border:none;border-radius:12px;padding:11px 22px;font-weight:800;}}"
            "QPushButton:disabled{background:#475569;color:#cbd5e1;}")
        self.save_btn.clicked.connect(self._save)
        bl.addWidget(self.save_btn)
        bar_wrap = QWidget()
        bw = QHBoxLayout(bar_wrap); bw.setContentsMargins(16, 0, 16, 8); bw.setSpacing(0)
        bw.addStretch(1); bw.addWidget(bar, 30); bw.addStretch(1)
        root.addWidget(bar_wrap)

        if not has_permission(current_user.role, Permission.CREATE_TXN):
            self.save_btn.setEnabled(False)
            self.save_btn.setText(_t("no_permission"))

        self.refresh()

    # -- builders -----------------------------------------------------
    def _field(self, label, widget, extra=None):
        col = QVBoxLayout(); col.setSpacing(4)
        cap = QLabel(label.upper())
        cap.setStyleSheet(f"color:{_c('muted')};font-size:11px;font-weight:700;letter-spacing:0.5px;")
        col.addWidget(cap)
        widget.setMinimumHeight(38)
        col.addWidget(widget)
        if extra is not None:
            extra.setFixedHeight(22)
            col.addWidget(extra)
        col.addStretch()
        return col

    def _stat(self, bar_layout, label, muted=False):
        box = QVBoxLayout(); box.setSpacing(2)
        cap = QLabel(label.upper())
        cap.setStyleSheet("color:#94a3b8;font-size:10px;font-weight:700;letter-spacing:0.6px;")
        val = QLabel("0.00")
        val.setStyleSheet(f"color:{'#cbd5e1' if muted else '#ffffff'};font-size:16px;font-weight:700;")
        box.addWidget(cap); box.addWidget(val)
        bar_layout.addLayout(box)
        return val

    def _add_row(self):
        row = _WoodRow(self._wood_types)
        row.changed.connect(self._recalc)
        row.removed.connect(self._remove_row)
        self._rows.append(row)
        self._rows_box.addWidget(row)
        self._recalc()

    def _remove_row(self, row):
        if len(self._rows) <= 1:
            return
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._recalc()

    # -- data ---------------------------------------------------------
    def refresh(self):
        from timber.core.ledger import all_party_balances

        with SessionLocal() as s:
            sups = s.scalars(select(Party).where(Party.party_type == PARTY_BAPARI, Party.is_active.is_(True)).order_by(Party.name)).all()
            facs = s.scalars(select(Party).where(Party.party_type == PARTY_FACTORY, Party.is_active.is_(True)).order_by(Party.name)).all()
            woods = s.scalars(select(WoodType).where(WoodType.is_active.is_(True)).order_by(WoodType.name)).all()
            self._sup_list = [(p.id, p.name) for p in sups]
            self._fac_list = [(p.id, p.name) for p in facs]
            self._wood_types = [
                (w.id, w.name,
                 float(w.default_supplier_rate or 0),
                 float(w.default_factory_rate or 0))
                for w in woods
            ]
            # EVERY party's balance in one batched pass (4 aggregate queries), so
            # picking a supplier/factory is an instant dict lookup instead of a
            # per-selection query (that query cost ~106ms on LAN, ~1s on cloud).
            self._balances = all_party_balances(s)
        for combo, items in ((self.supplier, self._sup_list), (self.factory, self._fac_list)):
            combo.blockSignals(True)
            combo.clear()
            for pid, name in items:
                combo.addItem(name, pid)
            combo.setCurrentIndex(-1)
            combo.blockSignals(False)
        if not self._rows:
            self._add_row()

    def _on_party(self, is_supplier):
        combo = self.supplier if is_supplier else self.factory
        label = self.sup_bal if is_supplier else self.fac_bal
        pid = combo.currentData()
        if not pid:
            label.setText(""); label.setStyleSheet(""); return
        # Instant: read the batched balances loaded in refresh() (no DB round-trip).
        internal = self._balances.get(pid, 0)
        disp = float(-internal if is_supplier else internal)
        if disp == 0:
            label.setText(_t("settled"))
            label.setStyleSheet(f"background:{_c('tab_bg')};color:{_c('muted')};padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700;")
        else:
            good = disp > 0
            fg = "#15803d" if good else "#b91c1c"
            bg = "#dcfce7" if good else "#fee2e2"
            if theme.get_theme() == "dark":
                fg = "#4ade80" if good else "#fca5a5"
                bg = "#14532d" if good else "#4c1d1d"
            label.setText(_money(disp))
            label.setStyleSheet(f"background:{bg};color:{fg};padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700;")

    # -- totals + save ------------------------------------------------
    def _recalc(self):
        purchase = sale = 0.0
        for r in self._rows:
            purchase += r.sup_w.value() * r.sup_r.value()
            sale += r.fac_w.value() * r.fac_r.value()
        by = {PAYER_US: 0.0, PAYER_FACTORY: 0.0, PAYER_BAPARI: 0.0}
        for c in (self.loading, self.freight, self.unloading):
            amt, p1, p2, split = c.values()
            if not amt:
                continue
            if p2:
                by[p1] += split
                by[p2] += amt - split
            else:
                by[p1] += amt
        freight_total = self.loading.amount.value() + self.freight.amount.value() + self.unloading.amount.value()
        supplier_net = purchase - (by[PAYER_FACTORY] + by[PAYER_US])
        factory_net = sale - by[PAYER_FACTORY]
        profit = sale - purchase
        self.t_purchase.setText(_money(purchase))
        self.t_sale.setText(_money(sale))
        self.t_freight.setText(_money(freight_total))
        self.t_supnet.setText(_money(supplier_net))
        self.t_facnet.setText(_money(factory_net))
        self.t_profit.setStyleSheet(f"color:{'#34d399' if profit >= 0 else '#fb7185'};font-size:22px;font-weight:900;")
        self.t_profit.setText(_money(profit))

    def _save(self):
        # Defence in depth: the button is disabled without the permission, but
        # re-check here so a stray signal can never write a trade.
        if not has_permission(self.current_user.role, Permission.CREATE_TXN):
            self._show_banner(False, _t("no_permission"))
            return
        sid = self.supplier.currentData()
        fid = self.factory.currentData()
        if not sid or not fid:
            self._show_banner(False, _t("select_supplier_factory"))
            return
        lam, lp, lp2, lsp = self.loading.values()
        fam, fp, fp2, fsp = self.freight.values()
        uam, up, up2, usp = self.unloading.values()
        try:
            with SessionLocal() as s:
                created = create_mixed_trade(
                    s, txn_date=self.date_edit.date().toPython(),
                    bapari_id=sid, factory_id=fid,
                    lines=[r.wood_line() for r in self._rows],
                    vehicle_no=self.vehicle.text().strip(),
                    loading_amount=lam, loading_payer=lp, loading_payer2=lp2, loading_split=lsp,
                    freight_amount=fam, freight_payer=fp, freight_payer2=fp2, freight_split=fsp,
                    unloading_amount=uam, unloading_payer=up, unloading_payer2=up2, unloading_split=usp,
                    created_by=self.current_user.id,
                )
                s.commit()
                profit = sum((c.profit for c in created), Decimal("0"))
                msg = f"{_t('saved')} — {len(created)} {_t('wood_lines')}, {_t('profit')} {_money(profit)}"
        except ValueError as exc:
            self._show_banner(False, str(exc))
            warn_toast(self, _t("cannot_save"), str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            err_toast(self, _t("error"), str(exc))
            return
        self._reload_balances()   # the trade moved both parties' balances
        self._show_banner(True, msg)
        info_toast(self, _t("saved"), msg)
        self._reset()

    def _reload_balances(self):
        """Re-read the batched balances after a save so the badges stay correct."""
        from timber.core.ledger import all_party_balances

        try:
            with SessionLocal() as s:
                self._balances = all_party_balances(s)
        except Exception:  # noqa: BLE001 - stale badges must never break saving
            pass

    def _show_banner(self, ok, msg):
        self.banner.setText(msg)
        if theme.get_theme() == "dark":
            style = ("background:#14532d;color:#86efac;" if ok else "background:#4c1d1d;color:#fca5a5;")
        else:
            style = (f"background:{design.tint(design.POS, 34)};color:{design.POS};" if ok
                     else f"background:{design.tint(design.NEG, 34)};color:{design.NEG};")
        self.banner.setStyleSheet(style + "border-radius:12px;padding:12px 16px;font-weight:600;")
        self.banner.setVisible(True)

    def _reset(self):
        for r in list(self._rows):
            r.setParent(None); r.deleteLater()
        self._rows.clear()
        self._add_row()
        self.vehicle.clear()
        for c in (self.loading, self.freight, self.unloading):
            c.reset()
        self._recalc()
        self._on_party(True)
        self._on_party(False)
