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
    QDateEdit,
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
from timber.ui import icons, theme
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


class _Card(QFrame):
    """White/dark rounded panel with an optional icon + title."""

    def __init__(self, title="", icon_name=""):
        super().__init__()
        self.setObjectName("rpCard")
        self.setStyleSheet(
            "#rpCard{background:" + _c("surface") + ";border:1px solid " + _c("border") + ";border-radius:16px;}")
        _shadow(self)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(20, 18, 20, 18)
        self.box.setSpacing(12)
        if title:
            head = QHBoxLayout(); head.setSpacing(9)
            if icon_name:
                ic = QLabel()
                try:
                    ic.setPixmap(icons.pixmap(icon_name, _c("accent"), 17))
                except Exception:  # noqa: BLE001
                    pass
                head.addWidget(ic)
            h = QLabel(title)
            h.setStyleSheet(f"color:{_c('text')};font-size:14px;font-weight:800;")
            head.addWidget(h); head.addStretch()
            self.box.addLayout(head)

    def add(self, w):
        self.box.addWidget(w)


TONES = {
    "indigo": "#6366f1", "sky": "#0ea5e9", "emerald": "#10b981",
    "amber": "#f59e0b", "rose": "#f43f5e", "violet": "#8b5cf6",
    "slate": "#64748b",
}


def _tint(hex_color: str, alpha: int = 38) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


class _Tile(QFrame):
    """KPI card matching the Dashboard's: tinted icon chip + label + value,
    with a coloured accent bar down the leading edge."""

    def __init__(self, label: str, value: str, color: str | None = None,
                 icon_name: str = "", tone: str = "slate"):
        super().__init__()
        self.setObjectName("rpTile")
        accent = TONES.get(tone, TONES["slate"])
        self.setStyleSheet(
            "#rpTile{background:" + _c("surface") + ";border:1px solid " + _c("border")
            + ";border-radius:16px;border-left:4px solid " + accent + ";}")
        _shadow(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 13, 16, 14); lay.setSpacing(9)

        top = QHBoxLayout(); top.setSpacing(9)
        chip = QLabel()
        chip.setFixedSize(32, 32)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setStyleSheet(f"background:{_tint(accent)};border-radius:9px;")
        try:
            chip.setPixmap(icons.pixmap(icon_name or "pie-chart", accent, 17))
        except Exception:  # noqa: BLE001
            pass
        cap = QLabel(label.upper())
        cap.setStyleSheet(f"color:{_c('muted')};font-size:11px;font-weight:700;letter-spacing:0.6px;")
        cap.setWordWrap(True)
        top.addWidget(chip); top.addWidget(cap, 1)
        lay.addLayout(top)

        val = QLabel(value)
        val.setStyleSheet(f"color:{color or _c('text')};font-size:21px;font-weight:800;")
        lay.addWidget(val)


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
        # Breathing room between the page title, the tab pills, the period
        # filter and the content (they were stacked almost edge to edge).
        outer.setContentsMargins(2, 4, 2, 0); outer.setSpacing(14)

        # sub-tabs
        self.segment = SegmentedControl([
            ("cashflow", _t("cash_flow"), "wallet"),
            ("factory", _t("factories"), "factory"),
            ("supplier", _t("suppliers"), "book-user"),
        ])
        self.segment.changed.connect(self._set_tab)
        tabrow = QHBoxLayout(); tabrow.addWidget(self.segment); tabrow.addStretch()
        outer.addLayout(tabrow)

        # period filter
        bar = QHBoxLayout(); bar.setSpacing(9)
        bar.setContentsMargins(0, 0, 0, 4)
        self.period_seg = SegmentedControl([
            ("all", _t("all_time"), ""), ("day", _t("today"), ""),
            ("month", _t("this_month"), ""), ("year", _t("this_year"), ""),
            ("custom", _t("custom"), ""),
        ], current="day", compact=True)
        self.period_seg.changed.connect(self._set_period)
        bar.addWidget(self.period_seg)
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
        scroll.setStyleSheet("QScrollArea{background:transparent;}")
        body = QWidget()
        self.v = QVBoxLayout(body)
        self.v.setContentsMargins(2, 2, 2, 8); self.v.setSpacing(16)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # PDF / Excel export, driven by the shared page toolbar. The builder is
        # called fresh on each click, so it always exports the tab + period the
        # user is looking at.
        self._report_builder = self._build_report
        self._report_name = "reports"

        self.refresh()

    def _build_report(self):
        """ReportData for the ACTIVE tab + period (same services as the screen)."""
        from timber.core.report_data import (
            cashflow_statement_report,
            party_performance_report,
        )

        start, end = self._range()
        with SessionLocal() as s:
            if self._tab == "cashflow":
                return cashflow_statement_report(s, start, end)
            ptype = PARTY_FACTORY if self._tab == "factory" else PARTY_BAPARI
            return party_performance_report(s, ptype, start, end)

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
            card = _Card(_t(CF_SECTIONS.get(sec, sec)))
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
            _Tile(_t("trades"), str(o["trades"]), None, "database", "slate"),
            _Tile(vol_label, _money(o["volume"]), None,
                  "receipt" if is_factory else "cart", "indigo" if is_factory else "sky"),
            _Tile(_t("profit"), _money(o["profit"]), _amt_color(o["profit"]),
                  "trending-up", "emerald"),
            _Tile(_t("to_receive"), _money(o["receivable"]), _amt_color(o["receivable"]),
                  "trending-up", "emerald"),
            _Tile(_t("to_give"), _money(-o["payable"]), _amt_color(-o["payable"]),
                  "trending-down", "rose"),
        ]
        if is_factory:
            tiles.append(_Tile(_t("overdue_30"), _money(o["over30"]),
                               "#d97706" if o["over30"] else None, "alarm-clock", "amber"))
            tiles.append(_Tile(_t("overdue_60"), _money(o["over60"]),
                               _NEG if o["over60"] else None, "alarm-clock", "rose"))
        wrap = QWidget(); tg = QGridLayout(wrap)
        tg.setContentsMargins(0, 0, 0, 0); tg.setSpacing(12)
        for i, tw in enumerate(tiles):
            tg.addWidget(tw, 0, i); tg.setColumnStretch(i, 1)
        self.v.addWidget(wrap)

        card = _Card(_t("factories") if is_factory else _t("suppliers"),
                     "factory" if is_factory else "book-user")
        headers = [_t("name"), _t("trades"), vol_label, _t("profit"), _t("balance")]
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
            tbl.setItem(i, 3, cell(_money(r["profit"]), _amt_color(r["profit"]), bold=True))
            tbl.setItem(i, 4, cell(_money(r["balance"]), _amt_color(r["balance"]), bold=True))
            if is_factory:
                tbl.setItem(i, 5, cell(_money(r["over30"]) if r["over30"] else "—",
                                       "#d97706" if r["over30"] else _c("muted")))
                tbl.setItem(i, 6, cell(_money(r["over60"]) if r["over60"] else "—",
                                       _NEG if r["over60"] else _c("muted")))
        tbl.setMinimumHeight(min(560, 70 + 34 * max(1, len(rows))))
        card.add(tbl)
        if not rows:
            empty = QLabel(_t("no_data_period"))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color:{_c('muted')};padding:22px;")
            card.add(empty)
        self.v.addWidget(card)
        self.v.addStretch()
