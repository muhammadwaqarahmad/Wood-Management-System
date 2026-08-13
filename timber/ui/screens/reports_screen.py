"""Reports — native, theme-aware page with three sub-tabs.

Cash flow / Factories / Suppliers, with the same period filter as the Dashboard.
All numbers come from ``stats_service.cashflow_report`` and
``stats_service.party_stats`` (logic unchanged); colours come from the active
theme palette and every label is an i18n key, so the page follows light/dark
AND translates.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.core.current_user import CurrentUser
from timber.db.engine import SessionLocal
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY
from timber.ui import design, icons, theme
from timber.ui.segmented import SegmentedControl

# Cash-flow row labels / section headings -> i18n keys (same rows as before).
CF_LABELS = {
    "banks": "banks", "cash": "cash", "available": "total_available",
    "cheques_in": "cheques_in", "unclaimed": "unclaimed",
    "receivable": "to_receive", "loans_given": "loans_given",
    "payable": "to_give", "loans": "loans_taken", "profit": "total_profit",
    "exp_business": "business_expenses", "exp_house": "house_expenses",
    "profit_after": "profit_after_expenses",
}
CF_SECTIONS = {
    "position": "cf_position", "balances": "cf_balances",
    "cheques": "cf_cheques", "unclaimed": "cf_unclaimed", "flows": "cf_flows",
}

_P: dict = {}
_P_THEME: str | None = None
_POS, _NEG, _ZERO = "#059669", "#e11d48", "#64748b"


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


def _shadow(w) -> None:
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(18); eff.setXOffset(0); eff.setYOffset(2)
    eff.setColor(QColor(15, 23, 42, 40 if theme.get_theme() == "dark" else 24))
    w.setGraphicsEffect(eff)


class _Rows(QFrame):
    """Borderless label / sign / amount rows (the cash-flow statement)."""

    def __init__(self):
        super().__init__()
        self.grid = QVBoxLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0); self.grid.setSpacing(0)

    def set_rows(self, rows):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for name, sign_txt, amount_txt, color, bold in rows:
            row = QWidget()
            row.setStyleSheet(f"border-bottom:1px solid {_c('border')};")
            hl = QHBoxLayout(row); hl.setContentsMargins(0, 8, 0, 8)
            n = QLabel(name)
            n.setStyleSheet(f"color:{_c('text')};font-size:13px;border:none;" + ("font-weight:800;" if bold else ""))
            hl.addWidget(n, 1)
            s = QLabel(sign_txt)
            s.setStyleSheet(f"color:{_c('muted')};font-size:11px;border:none;")
            s.setAlignment(Qt.AlignmentFlag.AlignCenter); s.setFixedWidth(24)
            hl.addWidget(s)
            a = QLabel(amount_txt)
            a.setStyleSheet(f"color:{color};font-size:13px;font-weight:700;border:none;")
            a.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            hl.addWidget(a)
            self.grid.addWidget(row)


class _ReportsExportDialog(design.Dialog):
    """Pick which sections go into the export, then choose PDF or Excel."""

    def __init__(self, current_tab, parent=None) -> None:
        super().__init__(_t("export"), "download", parent=parent, width=420)
        self.fmt = "pdf"
        hint = QLabel(_t("export_choose_sections"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{_c('muted')};font-size:12px;")
        self.body.addWidget(hint)

        self.cb_cash = QCheckBox(_t("cash_flow"))
        self.cb_fac = QCheckBox(_t("factories"))
        self.cb_sup = QCheckBox(_t("suppliers"))
        # Start with the tab the user is on ticked (never nothing).
        self.cb_cash.setChecked(current_tab == "cashflow")
        self.cb_fac.setChecked(current_tab == "factory")
        self.cb_sup.setChecked(current_tab == "supplier")
        # (Receivable & Giveable lives on the Financial Position page only.)
        for cb in (self.cb_cash, self.cb_fac, self.cb_sup):
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            self.body.addWidget(cb)

        pdf, _cancel = self.buttons(_t("export_pdf"))
        pdf.clicked.connect(lambda: self._go("pdf"))
        xls = QPushButton(_t("export_excel"))
        xls.setStyleSheet(design.btn("primary"))
        xls.setCursor(Qt.CursorShape.PointingHandCursor)
        xls.clicked.connect(lambda: self._go("xlsx"))
        self.add_button(xls)

    def _go(self, fmt: str) -> None:
        if not self.selection():
            return  # nothing ticked — keep the dialog open
        self.fmt = fmt
        self.accept()

    def selection(self) -> set:
        sel = set()
        if self.cb_cash.isChecked():
            sel.add("cashflow")
        if self.cb_fac.isChecked():
            sel.add("factory")
        if self.cb_sup.isChecked():
            sel.add("supplier")
        return sel


class ReportsScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        _refresh_palette()
        self.current_user = current_user
        self._tab = "cashflow"
        # Reports open on TODAY in every section; "All time" is one click away.
        self._period = "day"
        self._from = date.today() - timedelta(days=30)
        self._to = date.today()

        outer = QVBoxLayout(self)
        # Side inset matches the other pages so the tabs/filter/cards sit off
        # the panel's rounded edge (they used to hug it at 2px).
        outer.setContentsMargins(22, 8, 22, 0); outer.setSpacing(14)

        # sub-tabs
        self.segment = SegmentedControl([
            ("cashflow", _t("cash_flow"), "wallet"),
            ("factory", _t("factories"), "factory"),
            ("supplier", _t("suppliers"), "book-user"),
        ])
        self.segment.changed.connect(self._set_tab)
        tabrow = QHBoxLayout(); tabrow.addWidget(self.segment); tabrow.addStretch()
        # One main export: pick any of cash flow / factories / suppliers.
        self.export_btn = QPushButton(_t("export"))
        self.export_btn.setStyleSheet(design.btn("primary"))
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        try:
            self.export_btn.setIcon(icons.icon("download", "#ffffff", 15))
        except Exception:  # noqa: BLE001 - icon is decoration only
            pass
        self.export_btn.clicked.connect(self._open_export)
        tabrow.addWidget(self.export_btn)
        outer.addLayout(tabrow)

        # period filter — one compact dropdown (shows the current choice, click
        # to reveal all), defaulting to Day, consistent across the app.
        bar = QHBoxLayout(); bar.setSpacing(9)
        bar.setContentsMargins(0, 0, 0, 4)
        bar.addWidget(QLabel(_t("period") + ":"))
        self.period_combo = QComboBox()
        for key, label in (("all", _t("all_time")), ("day", _t("today")),
                           ("month", _t("this_month")), ("year", _t("this_year")),
                           ("custom", _t("custom"))):
            self.period_combo.addItem(label, key)
        self.period_combo.setCurrentIndex(self.period_combo.findData("day"))
        self.period_combo.currentIndexChanged.connect(
            lambda: self._set_period(self.period_combo.currentData()))
        bar.addWidget(self.period_combo)
        self._from_edit = QDateEdit(QDate(self._from.year, self._from.month, self._from.day))
        self._to_edit = QDateEdit(QDate(self._to.year, self._to.month, self._to.day))
        for e in (self._from_edit, self._to_edit):
            e.setCalendarPopup(True); e.setDisplayFormat("yyyy-MM-dd")
            e.setStyleSheet(
                f"QDateEdit{{background:{_c('input_bg')};border:1px solid {_c('input_border')};"
                f"border-radius:8px;padding:5px 8px;color:{_c('text')};}}")
            e.dateChanged.connect(self._on_dates); e.setVisible(False)
            bar.addWidget(e)
        bar.addStretch()
        outer.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;} QScrollArea > QWidget > QWidget{background:transparent;}")
        body = QWidget()
        self.v = QVBoxLayout(body)
        # outer already provides the side inset; keep the scroll body flush.
        self.v.setContentsMargins(0, 2, 0, 8); self.v.setSpacing(16)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # Export is the page's own "Export" button (opens a section picker), not
        # the shared top-right toolbar — so we do NOT set ``_report_builder``.

        self.refresh()

    def _open_export(self):
        """Pick which sections to export (cash flow / factories / suppliers),
        then write one combined PDF or Excel for the current period."""
        from timber.core.report_data import reports_combined_report
        from timber.ui.screens.export_helpers import run_export

        dlg = _ReportsExportDialog(self._tab, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sel = dlg.selection()
        if not sel:
            return
        start, end = self._range()

        def _build():
            with SessionLocal() as s:
                return reports_combined_report(s, sel, start, end)

        run_export(self, _build, "reports", dlg.fmt)

    # -- filters ------------------------------------------------------
    def _set_tab(self, v):
        self._tab = v
        self.refresh()

    def _set_period(self, v):
        self._period = v
        show = v == "custom"
        self._from_edit.setVisible(show); self._to_edit.setVisible(show)
        self.refresh()

    def _on_dates(self):
        d1, d2 = self._from_edit.date(), self._to_edit.date()
        self._from = date(d1.year(), d1.month(), d1.day())
        self._to = date(d2.year(), d2.month(), d2.day())
        if self._period == "custom":
            self.refresh()



    def _range(self):
        p, today = self._period, date.today()
        if p == "day":
            return today, today
        if p == "month":
            return date(today.year, today.month, 1), today
        if p == "year":
            return date(today.year, 1, 1), today
        if p == "custom":
            return self._from, self._to
        return None, None

    # -- data ---------------------------------------------------------
    def refresh(self):
        start, end = self._range()
        if self._tab == "cashflow":
            from timber.core.stats_service import cashflow_report
            with SessionLocal() as s:
                data = cashflow_report(s, start, end)
            self._build_cashflow(data)
        else:
            from timber.core.stats_service import party_stats
            ptype = PARTY_FACTORY if self._tab == "factory" else PARTY_BAPARI
            with SessionLocal() as s:
                data = party_stats(s, ptype, start, end)
            self._build_parties(data, self._tab == "factory")

    def _clear(self):
        while self.v.count():
            it = self.v.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _build_cashflow(self, data):
        self._clear()
        hero = QFrame(); hero.setObjectName("cfHero")
        hero.setStyleSheet(
            "#cfHero{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 "
            + _c("accent") + ",stop:1 " + _c("accent2") + ");border-radius:16px;}")
        _shadow(hero)
        hl = QVBoxLayout(hero); hl.setContentsMargins(24, 20, 24, 20); hl.setSpacing(4)
        cap = QLabel(_t("total_business_worth").upper())
        cap.setStyleSheet("color:#dbeafe;font-size:11px;font-weight:800;letter-spacing:1.4px;")
        worth = data["worth"]
        val = QLabel(_money(worth))
        val.setStyleSheet(f"color:{'#fecaca' if worth < 0 else '#ffffff'};font-size:30px;font-weight:900;")
        hl.addWidget(cap); hl.addWidget(val)
        self.v.addWidget(hero)

        sections: list[tuple[str, list]] = []
        for r in data["rows"]:
            if r["section"] == "worth":
                continue
            if not sections or sections[-1][0] != r["section"]:
                sections.append((r["section"], [r]))
            else:
                sections[-1][1].append(r)

        grid = QWidget(); g = QGridLayout(grid)
        g.setContentsMargins(0, 0, 0, 0); g.setSpacing(16)
        for idx, (sec, rows) in enumerate(sections):
            card = design.Card(_t(CF_SECTIONS.get(sec, sec)), "wallet")
            tbl = _Rows()
            kv = []
            for r in rows:
                amt, sign = r["amount"], r["sign"]
                disp = amt if sign == 0 else sign * amt
                sign_txt = "+" if sign > 0 else "−" if sign < 0 else "="
                kv.append((_t(CF_LABELS.get(r["key"], r["key"])), sign_txt,
                           _money(-amt if sign < 0 else amt), _amt_color(disp), sign == 0))
            tbl.set_rows(kv)
            card.add(tbl)
            g.addWidget(card, idx // 2, idx % 2)
        g.setColumnStretch(0, 1); g.setColumnStretch(1, 1)
        self.v.addWidget(grid)
        self.v.addStretch()

    def _build_parties(self, data, is_factory):
        self._clear()
        o = data["overall"]
        vol_label = _t("total_sales") if is_factory else _t("total_purchases")
        tiles = [
            design.Tile(_t("trades"), str(o["trades"]), "database", "slate"),
            design.Tile(vol_label, _money(o["volume"]),
                        "receipt" if is_factory else "cart",
                        "indigo" if is_factory else "sky"),
            design.Tile(_t("profit"), _money(o["profit"]), "trending-up", "emerald",
                        _amt_color(o["profit"])),
            design.Tile(_t("to_receive"), _money(o["receivable"]), "trending-up",
                        "emerald", _amt_color(o["receivable"])),
            design.Tile(_t("to_give"), _money(-o["payable"]), "trending-down", "rose",
                        _amt_color(-o["payable"])),
        ]
        if is_factory:
            tiles.append(design.Tile(_t("overdue_30"), _money(o["over30"]),
                                     "alarm-clock", "amber",
                                     "#d97706" if o["over30"] else None))
            tiles.append(design.Tile(_t("overdue_60"), _money(o["over60"]),
                                     "alarm-clock", "rose",
                                     _NEG if o["over60"] else None))
        wrap = QWidget(); tg = QGridLayout(wrap)
        tg.setContentsMargins(0, 0, 0, 0); tg.setSpacing(12)
        for i, tw in enumerate(tiles):
            tg.addWidget(tw, 0, i); tg.setColumnStretch(i, 1)
        self.v.addWidget(wrap)

        card = design.Card(_t("factories") if is_factory else _t("suppliers"),
                           "factory" if is_factory else "book-user")
        headers = [_t("name"), _t("trades"), vol_label, _t("to_receive"), _t("to_give")]
        if is_factory:
            headers += [_t("overdue_30"), _t("overdue_60")]
        rows = data["rows"]
        tbl = QTableWidget(len(rows), len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setShowGrid(False)
        tbl.setAlternatingRowColors(True)
        tbl.setStyleSheet(
            f"QTableWidget{{background:transparent;border:none;color:{_c('text')};"
            f"alternate-background-color:{_c('alt_row')};}}"
            f"QHeaderView::section{{background:transparent;color:{_c('muted')};border:none;"
            f"border-bottom:2px solid {_c('border')};padding:7px 6px;font-size:11px;font-weight:700;}}")
        hdr = tbl.horizontalHeader()
        # Name stretched while every figure column was ResizeToContents, so the
        # name absorbed ALL the slack and the numbers were squeezed to their
        # bare minimum. Give the figures a comfortable floor and cap the name
        # so it takes a share rather than the remainder.
        hdr.setMinimumSectionSize(112)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        tbl.setColumnWidth(0, 240)
        for cidx in range(1, len(headers)):
            hdr.setSectionResizeMode(cidx, QHeaderView.ResizeMode.Stretch)
        tbl.setWordWrap(False)
        tbl.setTextElideMode(Qt.TextElideMode.ElideRight)

        def cell(text, color=None, right=True, bold=False):
            it = QTableWidgetItem(text)
            it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (
                Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft))
            if color:
                it.setForeground(QBrush(QColor(color)))
            if bold:
                f = it.font(); f.setBold(True); it.setFont(f)
            return it

        for i, r in enumerate(rows):
            tbl.setItem(i, 0, cell(r["name"], _c("text"), right=False, bold=True))
            tbl.setItem(i, 1, cell(str(r["trades"]), _c("text")))
            tbl.setItem(i, 2, cell(_money(r["volume"]), _c("text")))
            # balance is display-signed (+ we receive, - we give); split it into
            # two columns so each party's amount shows under the right heading.
            bal = r["balance"]
            tbl.setItem(i, 3, cell(_money(bal) if bal > 0 else "—",
                                   _POS if bal > 0 else _ZERO, bold=(bal > 0)))
            tbl.setItem(i, 4, cell(_money(-bal) if bal < 0 else "—",
                                   _NEG if bal < 0 else _ZERO, bold=(bal < 0)))
            if is_factory:
                tbl.setItem(i, 5, cell(_money(r["over30"]) if r["over30"] else "—",
                                       "#d97706" if r["over30"] else _c("muted")))
                tbl.setItem(i, 6, cell(_money(r["over60"]) if r["over60"] else "—",
                                       _NEG if r["over60"] else _c("muted")))
        tbl.setMinimumHeight(min(560, 70 + 34 * max(1, len(rows))))
        if rows:
            card.add(tbl)
        else:
            card.add(design.empty_state(
                _t("no_data_period"), "",
                "factory" if is_factory else "book-user"))
        self.v.addWidget(card)
        self.v.addStretch()
