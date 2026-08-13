"""Dashboard — native, theme-aware overview page.

A period filter, a "Period summary" tile row, a "Financial position" tile row,
two grouped bar charts, and Summary + Bank-balance tables, plus PDF/Excel
export. All numbers come from ``dashboard_service.dashboard_summary``
(unchanged); colours come from the active theme palette and every label is an
i18n key, so the page follows light/dark AND translates.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.core.current_user import CurrentUser
from timber.db.engine import SessionLocal
from timber.ui import design, icons, theme
from timber.ui.segmented import SegmentedControl

# Tone accents for the KPI tiles (kept vivid in both themes).
TONES = {
    "indigo": "#6366f1", "sky": "#0ea5e9", "emerald": "#10b981",
    "amber": "#f59e0b", "rose": "#f43f5e", "violet": "#8b5cf6",
    "slate": "#64748b",
}
# Chart series colours, assigned from a FIXED categorical order (never cycled)
# and validated for colour-vision deficiency in both modes. The old set paired
# #10b981 with #22c55e — two near-identical greens — and failed CVD separation
# outright (profit vs expenses ΔE 5.7 protan, below the 8 floor).
_CAT_LIGHT = ["#2a78d6", "#008300", "#e87ba4", "#eda100"]   # blue, green, magenta, yellow
_CAT_DARK = ["#3987e5", "#008300", "#d55181", "#c98500"]


def _series_colours() -> dict:
    """{key: hex} for the chart series in the ACTIVE theme."""
    ramp = _CAT_DARK if theme.get_theme() == "dark" else _CAT_LIGHT
    # Fixed slot order: sales, purchases, profit, expenses.
    return {"sales": ramp[0], "purchases": ramp[1],
            "profit": ramp[2], "expenses": ramp[3]}

_P: dict = {}
_P_THEME: str | None = None
POS, NEG, ZERO_C = "#059669", "#e11d48", "#64748b"


def _refresh_palette() -> None:
    global _P, _P_THEME, POS, NEG, ZERO_C
    _P = theme.palette()
    _P_THEME = theme.get_theme()
    dark = theme.get_theme() == "dark"
    POS = "#34d399" if dark else "#059669"
    NEG = "#fb7185" if dark else "#e11d48"
    ZERO_C = _P.get("muted", "#64748b")


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


def _money(v: float, dec: int = 2) -> str:
    return f"{v:,.{dec}f}"


def _amt_color(v: float) -> str:
    return POS if v > 0 else NEG if v < 0 else ZERO_C


def _tint(hex_color: str, alpha: int = 30) -> str:
    """Translucent version of a tone colour — works on light AND dark cards."""
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def _shadow(w) -> None:
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(20); eff.setXOffset(0); eff.setYOffset(3)
    eff.setColor(QColor(15, 23, 42, 45 if theme.get_theme() == "dark" else 26))
    w.setGraphicsEffect(eff)


def _Tile(icon_name, label, value, tone, signed=False, plain=False) -> QFrame:
    """A KPI tile — a thin wrapper over the shared ``design.stat_tile`` so every
    tile in the app is the one component (accent bar + tinted icon chip +
    value). ``signed`` colours the value green/red; ``plain`` shows it as text."""
    accent = TONES.get(tone, TONES["slate"])
    text = str(value) if plain else _money(value, 1)
    col = _amt_color(value) if signed else _c("text")
    frame, _val = design.stat_tile(label, accent, icon_name, value=text, value_color=col)
    return frame


class _Card(QFrame):
    """Rounded panel with a title, for the charts and tables."""

    def __init__(self, title, icon_name=""):
        super().__init__()
        self.setObjectName("dashCard")
        self.setStyleSheet(
            "#dashCard{background:" + _c("surface") + ";border-radius:16px;border:1px solid "
            + _c("border") + ";}")
        _shadow(self)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(20, 17, 20, 18)
        self.box.setSpacing(12)
        head = QHBoxLayout(); head.setSpacing(9)
        if icon_name:
            ic = QLabel()
            ic.setFixedSize(26, 26)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ic.setStyleSheet(
                "border-radius:8px;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f"stop:0 {_c('accent')},stop:1 {_tint(_c('accent'), 60)});")
            try:
                ic.setPixmap(icons.pixmap(icon_name, "#ffffff", 15))
            except Exception:  # noqa: BLE001
                pass
            head.addWidget(ic)
        h = QLabel(title)
        h.setStyleSheet(f"color:{_c('text')};font-size:15px;font-weight:800;")
        head.addWidget(h); head.addStretch()
        self.box.addLayout(head)

    def add(self, w):
        self.box.addWidget(w)


class _BarChart(QWidget):
    """Grouped bar chart: hairline grid, K/M ticks, rounded bars, legend."""

    def __init__(self, series):
        super().__init__()
        self._series = series  # [(key, name, color)]
        self._data = []
        self._hit = []
        self.setMinimumHeight(250)
        # A chart the user can point at should answer. Exact figures live in
        # the tooltip so the plot itself stays free of a number per bar.
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt override
        from PySide6.QtWidgets import QToolTip

        pos = event.position() if hasattr(event, "position") else event.pos()
        for rect, name, value, _col in self._hit:
            # A slightly larger hit target than the mark itself.
            if rect.adjusted(-3, -3, 3, 3).contains(pos):
                QToolTip.showText(event.globalPosition().toPoint()
                                  if hasattr(event, "globalPosition")
                                  else event.globalPos(),
                                  f"{name}: {_money(value)}", self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

    def set_data(self, data):
        self._data = list(data)[-24:]
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt override
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        import math

        W, H = self.width(), self.height()
        padB, padT, padR = 26, 26, 10
        grid_col = QColor(_c("border"))
        muted = QColor(_c("muted"))

        if not self._data:
            p.setPen(muted)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, _t("no_data_period"))
            p.end()
            return

        keys = [s[0] for s in self._series]
        vals = [float(row.get(k, 0) or 0) for row in self._data for k in keys]
        maxV = max([1.0] + vals)
        minV = min([0.0] + vals)

        # Round the axis to "nice" round numbers so the full-number ticks read
        # cleanly (e.g. 400,000 — not 402,999) instead of K/M abbreviations.
        def _nice(x, round_):
            if x <= 0:
                return 1.0
            exp = math.floor(math.log10(x))
            f = x / 10 ** exp
            if round_:
                nf = 1 if f < 1.5 else 2 if f < 3 else 5 if f < 7 else 10
            else:
                nf = 1 if f <= 1 else 2 if f <= 2 else 5 if f <= 5 else 10
            return nf * 10 ** exp

        step = _nice(_nice(maxV - minV, False) / 4, True)
        minV = math.floor(minV / step) * step
        maxV = math.ceil(maxV / step) * step
        span = (maxV - minV) or 1.0
        nticks = int(round(span / step)) + 1

        # Full-number tick labels, so the gutter must fit the widest one.
        p.setFont(QFont("", 8))
        fm = p.fontMetrics()
        tick_labels = [f"{minV + step * i:,.0f}" for i in range(nticks)]
        padL = max(fm.horizontalAdvance(t) for t in tick_labels) + 14

        def yy(v):
            return padT + (H - padT - padB) * (1 - (v - minV) / span)

        lx = padL
        for _k, name, color in self._series:
            p.fillRect(lx, padT - 18, 10, 10, QColor(color))
            p.setPen(muted)
            p.drawText(lx + 14, padT - 9, name)
            lx += 24 + fm.horizontalAdvance(name)

        for i in range(nticks):
            tv = minV + step * i
            gy = yy(tv)
            p.setPen(QPen(grid_col, 1))
            p.drawLine(padL, int(gy), W - padR, int(gy))
            p.setPen(muted)
            p.drawText(0, int(gy) - 6, padL - 8, 12,
                       Qt.AlignmentFlag.AlignRight, tick_labels[i])

        y0 = yy(0)
        p.setPen(QPen(grid_col, 1))
        p.drawLine(padL, int(y0), W - padR, int(y0))

        n = len(self._data)
        plotW = W - padL - padR
        groupW = plotW / max(1, n)
        ns = len(self._series)
        # 2px gap between adjacent bars so touching fills stay separable —
        # this is the secondary encoding the CVD floor relies on.
        gap = 2
        barW = max(3, min(22, (groupW - 8) / ns - gap))
        self._hit = []          # [(QRectF, series_name, value, colour)] for hover
        for i, row in enumerate(self._data):
            gx = padL + i * groupW + (groupW - ns * (barW + gap)) / 2
            for j, (k, _name, color) in enumerate(self._series):
                v = float(row.get(k, 0) or 0)
                top = min(yy(v), y0)
                hgt = max(2, abs(yy(v) - y0))
                x = gx + j * (barW + gap)
                # Round only the DATA END; the baseline end stays square so the
                # bar reads as anchored to the axis rather than floating.
                r = min(4, barW / 2, hgt)
                path = QPainterPath()
                if hgt <= r * 2:
                    path.addRect(x, top, barW, hgt)
                elif v >= 0:
                    path.moveTo(x, top + hgt)
                    path.lineTo(x, top + r)
                    path.quadTo(x, top, x + r, top)
                    path.lineTo(x + barW - r, top)
                    path.quadTo(x + barW, top, x + barW, top + r)
                    path.lineTo(x + barW, top + hgt)
                    path.closeSubpath()
                else:
                    b = top + hgt
                    path.moveTo(x, top)
                    path.lineTo(x, b - r)
                    path.quadTo(x, b, x + r, b)
                    path.lineTo(x + barW - r, b)
                    path.quadTo(x + barW, b, x + barW, b - r)
                    path.lineTo(x + barW, top)
                    path.closeSubpath()
                p.fillPath(path, QColor(color))
                from PySide6.QtCore import QRectF
                self._hit.append((QRectF(x, top, barW, hgt), _name, v, color))
            if n <= 8 or i % max(1, n // 8) == 0:
                p.setPen(muted)
                lab = str(row.get("label", ""))
                lab = lab[5:] if len(lab) > 7 else lab
                p.drawText(int(padL + i * groupW), H - 16, int(groupW), 12,
                           Qt.AlignmentFlag.AlignCenter, lab)
        p.end()


class _KVTable(QFrame):
    """Borderless rows table (Summary / Bank balances)."""

    def __init__(self):
        super().__init__()
        self.grid = QVBoxLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)

    def set_rows(self, rows):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for name, sign_txt, amount_txt, color, bold in rows:
            row = QWidget()
            row.setStyleSheet(f"border-bottom:1px solid {_c('border')};")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 7, 0, 7)
            n = QLabel(name)
            n.setStyleSheet(f"color:{_c('text')};font-size:13px;border:none;"
                            + ("font-weight:800;" if bold else ""))
            hl.addWidget(n, 1)
            if sign_txt is not None:
                s = QLabel(sign_txt)
                s.setStyleSheet(f"color:{_c('muted')};font-size:11px;border:none;")
                s.setAlignment(Qt.AlignmentFlag.AlignCenter)
                s.setFixedWidth(24)
                hl.addWidget(s)
            a = QLabel(amount_txt)
            a.setStyleSheet(f"color:{color};font-size:13px;font-weight:700;border:none;")
            a.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            hl.addWidget(a)
            self.grid.addWidget(row)


_LBL = {
    "banks": "banks", "cash": "cash", "receivable": "to_receive",
    "loans_given": "loans_given", "payable": "to_give", "loans": "loans_taken",
    "net_worth": "net_position",
}


class DashboardScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        _refresh_palette()
        self.current_user = current_user
        # Opens on TODAY: the daily figures are what the desk actually
        # works from. "All time" is one click away.
        self._period = "day"
        self._from = date.today() - timedelta(days=30)
        self._to = date.today()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QHBoxLayout()
        # Real side padding so the filter/cards sit inset from the panel edge
        # (they used to hug the rounded corner at 2px). Room above/below too.
        bar.setContentsMargins(22, 16, 22, 16)
        bar.setSpacing(9)
        # One compact period dropdown (shows the current choice, click to reveal
        # all), defaulting to Day — consistent with every other page.
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
            e.setCalendarPopup(True)
            e.setDisplayFormat("yyyy-MM-dd")
            e.setStyleSheet(
                f"QDateEdit{{background:{_c('input_bg')};border:1px solid {_c('input_border')};"
                f"border-radius:8px;padding:5px 8px;color:{_c('text')};}}")
            e.dateChanged.connect(self._on_dates)
            e.setVisible(False)
            bar.addWidget(e)
        bar.addStretch()
        outer.addLayout(bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;} QScrollArea > QWidget > QWidget{background:transparent;}")
        body = QWidget()
        self.v = QVBoxLayout(body)
        # Match the filter bar's side inset; keep the panel content off the edge.
        self.v.setContentsMargins(22, 0, 22, 14)
        self.v.setSpacing(20)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        # PDF / Excel export via the shared page toolbar (built fresh per click).
        self._report_builder = self._build_report
        self._report_name = "dashboard"

        self.refresh()

    def _build_report(self):
        from timber.core.report_data import dashboard_report

        start, end = self._range()
        with SessionLocal() as s:
            return dashboard_report(s, start, end)

    def _set_period(self, v):
        self._period = v
        show = v == "custom"
        self._from_edit.setVisible(show)
        self._to_edit.setVisible(show)
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

    def refresh(self):
        start, end = self._range()
        from timber.core.dashboard_service import dashboard_summary

        with SessionLocal() as s:
            data = dashboard_summary(s, start, end)
        self._build(data)

    def _clear(self):
        while self.v.count():
            it = self.v.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _tile_section(self, title, tiles, cols):
        """A heading and its tiles as ONE block.

        They used to be two separate children of a 20px-spaced column, so the
        heading floated a full section-gap above the cards it labels. Grouped,
        the caption sits 6px above its own row and the 20px only separates
        one section from the next.
        """
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        lbl = QLabel(title.upper())
        lbl.setStyleSheet(
            f"color:{_c('text')};font-size:12px;font-weight:800;letter-spacing:1.0px;"
            "padding:0 0 0 2px;")
        outer.addWidget(lbl)

        grid_host = QWidget()
        g = QGridLayout(grid_host)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(12)
        for i, tw in enumerate(tiles):
            g.addWidget(tw, i // cols, i % cols)
        for cc in range(cols):
            g.setColumnStretch(cc, 1)
        outer.addWidget(grid_host)
        self.v.addWidget(wrap)

    def _build(self, data):
        self._clear()
        c = data["cards"]

        self._tile_section(_t("period_summary"), [
            _Tile("receipt", _t("sale_bill"), c["sales"], "indigo"),
            _Tile("cart", _t("purchase_bill"), c["purchases"], "sky"),
            _Tile("trending-up", _t("profit"), c["profit"], "emerald", signed=True),
            _Tile("trending-down", _t("business_expenses"), c["expBusiness"], "amber"),
            _Tile("trending-down", _t("house_expenses"), c["expHouse"], "amber"),
            _Tile("database", _t("trades"), c["trades"], "slate", plain=True),
        ], 6)

        self._tile_section(_t("financial_position"), [
            _Tile("landmark", _t("banks"), c["bankTotal"], "indigo"),
            _Tile("wallet", _t("cash"), c["cash"], "indigo"),
            _Tile("pie-chart", _t("available"), c["available"], "violet", signed=True),
            _Tile("info", _t("unclaimed_total"), c["unclaimed"], "amber"),
            _Tile("trending-up", _t("to_receive"), c["receivable"], "emerald", signed=True),
            _Tile("trending-down", _t("to_give"), c["payable"], "rose", signed=True),
            _Tile("hand-coins", _t("loans_taken"), c["loans"], "rose", signed=True),
            _Tile("hand-coins", _t("loans_given"), c["loansGiven"], "emerald", signed=True),
        ], 4)

        charts = QWidget()
        cg = QGridLayout(charts)
        cg.setContentsMargins(0, 0, 0, 0)
        cg.setSpacing(16)
        CH = _series_colours()
        c1 = _Card(_t("sales_purchases"), "trending-up")
        ch1 = _BarChart([("sales", _t("sale_bill"), CH["sales"]),
                         ("purchases", _t("purchase_bill"), CH["purchases"])])
        ch1.set_data(data["series"])
        c1.add(ch1)
        c2 = _Card(_t("profit_expenses"), "pie-chart")
        ch2 = _BarChart([("profit", _t("profit"), CH["profit"]),
                         ("expenses", _t("expenses"), CH["expenses"])])
        ch2.set_data(data["series"])
        c2.add(ch2)
        cg.addWidget(c1, 0, 0)
        cg.addWidget(c2, 0, 1)
        cg.setColumnStretch(0, 1)
        cg.setColumnStretch(1, 1)
        self.v.addWidget(charts)

        tables = QWidget()
        tg = QGridLayout(tables)
        tg.setContentsMargins(0, 0, 0, 0)
        tg.setSpacing(16)
        sc = _Card(_t("summary"), "book-text")
        st = _KVTable()
        srows = []
        for r in data["table"]:
            amt, sign = r["amount"], r["sign"]
            disp = amt if sign == 0 else sign * amt
            sign_txt = "+" if sign > 0 else "−" if sign < 0 else "="
            srows.append((_t(_LBL.get(r["key"], r["key"])), sign_txt,
                          _money(-amt if sign < 0 else amt), _amt_color(disp), sign == 0))
        st.set_rows(srows)
        sc.add(st)
        bc = _Card(_t("bank_balances"), "landmark")
        bt = _KVTable()
        banks = data["banks"]
        bank_rows = [(b["name"], None, _money(b["balance"]),
                      _amt_color(b["balance"]), False) for b in banks]

        # With ~28 accounts this list ran far past everything beside it and
        # dragged the whole row's height with it. Show the first few and let
        # the user open the rest.
        LIMIT = 8
        bt.set_rows(bank_rows[:LIMIT])
        bc.add(bt)
        if len(bank_rows) > LIMIT:
            more = QPushButton()
            more.setCursor(Qt.CursorShape.PointingHandCursor)
            more.setStyleSheet(
                f"QPushButton{{background:transparent;color:{_c('accent')};border:none;"
                "font-size:12px;font-weight:700;padding:6px 2px;text-align:left;}"
                f"QPushButton:hover{{color:{_c('text')};}}")

            def _toggle(_=False, _bt=bt, _btn=more, _rows=bank_rows):
                showing_all = _btn.property("expanded") or False
                _bt.set_rows(_rows if not showing_all else _rows[:LIMIT])
                _btn.setProperty("expanded", not showing_all)
                _btn.setText(
                    _t("show_less") if not showing_all
                    else f"{_t('show_all')} ({len(_rows)})"
                )

            more.setText(f"{_t('show_all')} ({len(bank_rows)})")
            more.clicked.connect(_toggle)
            bc.add(more)

        tg.addWidget(sc, 0, 0)
        tg.addWidget(bc, 0, 1)
        tg.setColumnStretch(0, 1)
        tg.setColumnStretch(1, 1)
        # Size each card to ITS OWN content. Without this the shorter Summary
        # card was stretched to match the tall bank list, leaving the large
        # empty area beside it.
        tg.setAlignment(sc, Qt.AlignmentFlag.AlignTop)
        tg.setAlignment(bc, Qt.AlignmentFlag.AlignTop)
        self.v.addWidget(tables)
        self.v.addStretch()
