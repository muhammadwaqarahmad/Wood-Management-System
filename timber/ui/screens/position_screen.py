"""Financial Position — the firm-wide summary the client keeps by hand.

Built like the Master Data page: a tab per section, each fully self-
contained (its own summary cards, its own table, its own export). Nothing
from one tab bleeds into another.
  * Bank        — daily balance of every account.
  * To receive  — everyone who owes us, amount positive.
  * To give     — everyone we owe (suppliers + loans), amount negative.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.ui import design
from timber.ui.segmented import SegmentedControl
from timber.core.current_user import CurrentUser
from timber.core.position import financial_position
from timber.core.report_data import ReportData, position_report
from timber.db.engine import SessionLocal
from timber.ui.screens.export_helpers import export_buttons
from timber.ui.screens.table_utils import (
    BAL_GREEN,
    BAL_RED,
    SearchBox,
    colour_cell,
    fill_table,
    fmt,
    make_table,
)

_ACCENT_BLUE = "#3b82f6"
_ACCENT_AMBER = "#d97706"
_ACCENT_SLATE = "#64748b"


def _money_colour(value) -> str:
    if value < 0:
        return BAL_RED
    if value > 0:
        return BAL_GREEN
    return _ACCENT_SLATE


def _kind_key(kind: str) -> str:
    return {"supplier": "bapari", "factory": "factory", "loan": "loan"}.get(kind, kind)


def _kpi_card(title: str, value: str, accent: str) -> QFrame:
    """The shared KPI tile: caption over an accent value, bar on the leading
    edge. This used to hard-code a dark slate card, so on the light theme it
    sat as a dark block in the middle of a light page.
    """
    from timber.ui import design

    design.refresh()
    frame = QFrame()
    frame.setObjectName("kpi")
    frame.setStyleSheet(
        "QFrame#kpi {"
        f"  background: {design.c('surface')};"
        f"  border: 1px solid {design.c('border')};"
        f"  border-left: 4px solid {accent};"
        "  border-radius: 16px;"
        "}"
        "QLabel { background: transparent; border: none; }"
    )
    box = QVBoxLayout(frame)
    box.setContentsMargins(16, 13, 16, 14)
    box.setSpacing(8)
    t = QLabel(title.upper())
    t.setWordWrap(True)
    t.setStyleSheet(
        f"color:{design.c('muted')};font-size:11px;font-weight:700;letter-spacing:0.6px;"
    )
    v = QLabel(value)
    v.setStyleSheet(f"color:{accent};font-size:21px;font-weight:800;")
    box.addWidget(t)
    box.addWidget(v)
    frame.setMinimumHeight(78)
    design.shadow(frame, blur=20, dy=3)
    return frame


class _PositionPanel(QWidget):
    """One tab of the Financial Position page."""

    def __init__(self, section: str, parent=None) -> None:
        super().__init__(parent)
        self.section = section
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 8, 4, 4)
        root.setSpacing(10)

        # This section's export buttons. They are NOT added here — the page
        # hosts them beside the section switcher so the switcher, the search
        # and the exports share one row.
        self.export_btns = export_buttons(
            self, self._report, f"position_{section}", as_widgets=True)

        # Summary cards for this section (rebuilt each refresh).
        self.cards = QWidget()
        self.cards_layout = QHBoxLayout(self.cards)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        root.addWidget(self.cards)

        if section == "bank":
            cols = [i18n.tr("name"), i18n.tr("bank_name"), i18n.tr("balance")]
        else:
            cols = [i18n.tr("name"), i18n.tr("contact"),
                    i18n.tr("type"), i18n.tr("amount")]
        self.table = make_table(cols)
        self.search = SearchBox(self.table)   # hosted in the page's top row
        root.addWidget(self.table, 1)

    def _report(self) -> ReportData:
        with SessionLocal() as session:
            return position_report(session, self.section)

    def _clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def update_data(self, pos) -> None:
        self._clear_cards()
        if self.section == "bank":
            self._fill_bank(pos)
        elif self.section == "receivable":
            self._fill_parties(pos.receivables, pos.total_receivable,
                               i18n.tr("to_receive"), BAL_GREEN)
        else:
            self._fill_parties(pos.payables, pos.total_payable,
                               i18n.tr("to_give"), BAL_RED)
        self.search.apply()

    def _fill_bank(self, pos) -> None:
        cards = [
            (i18n.tr("bank_total"), fmt(pos.bank_total), _ACCENT_BLUE),
            (i18n.tr("cash_position"), fmt(pos.cash_balance),
             _money_colour(pos.cash_balance)),
            (i18n.tr("cheque_balance"), fmt(pos.cheque_total), _ACCENT_AMBER),
        ]
        # Unattributed money is already inside the grand total; show it as its
        # own card only when there is some waiting to be claimed.
        if pos.unclaimed_total > 0:
            cards.append(
                (i18n.tr("unclaimed_total"), fmt(pos.unclaimed_total), _ACCENT_AMBER)
            )
        cards.append(
            (i18n.tr("grand_total"), fmt(pos.grand_total),
             _money_colour(pos.grand_total))
        )
        for title, value, accent in cards:
            self.cards_layout.addWidget(_kpi_card(title, value, accent))
        fill_table(self.table, [
            [a.name, a.bank_name or "", fmt(a.closing)] for a in pos.accounts
        ])
        for i, a in enumerate(pos.accounts):
            colour_cell(self.table, i, 2, _money_colour(a.closing))

    def _fill_parties(self, rows, total, label, accent) -> None:
        self.cards_layout.addWidget(_kpi_card(label, fmt(total), accent))
        self.cards_layout.addWidget(
            _kpi_card(i18n.tr("parties"), str(len(rows)), _ACCENT_SLATE)
        )
        self.cards_layout.addStretch()
        fill_table(self.table, [
            [r.name, r.contact, i18n.tr(_kind_key(r.kind)), fmt(r.amount)]
            for r in rows
        ])
        for i in range(len(rows)):
            colour_cell(self.table, i, 3, accent)


class PositionScreen(QWidget):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        design.refresh()
        root = QVBoxLayout(self)
        root.setSpacing(14)

        # An always-visible headline. This is the post-login landing page, and
        # previously every figure was hidden behind one of the three sections —
        # you had to click around to learn where the business stands.
        tiles = QHBoxLayout()
        tiles.setSpacing(14)
        t_avail, self.tile_available = design.stat_tile(
            i18n.tr("total_available"), design.c("accent"), "wallet")
        t_recv, self.tile_receivable = design.stat_tile(
            i18n.tr("to_receive"), design.TONES["emerald"], "trending-up")
        t_pay, self.tile_payable = design.stat_tile(
            i18n.tr("to_give"), design.TONES["rose"], "trending-down")
        t_chq, self.tile_cheques = design.stat_tile(
            i18n.tr("cheque_balance"), design.TONES["amber"], "file-check")
        t_net, self.tile_net = design.stat_tile(
            i18n.tr("net_worth"), design.TONES["violet"], "pie-chart")
        for t in (t_avail, t_recv, t_pay, t_chq, t_net):
            tiles.addWidget(t, 1)
        root.addLayout(tiles)

        # The last QTabWidget in the app — every other page switches with the
        # shared segmented control, so this one now matches.
        self.bank_panel = _PositionPanel("bank")
        self.recv_panel = _PositionPanel("receivable")
        self.pay_panel = _PositionPanel("payable")

        specs = [
            ("bank", i18n.tr("bank_total"), "landmark"),
            ("receivable", i18n.tr("to_receive"), "trending-up"),
            ("payable", i18n.tr("to_give"), "trending-down"),
        ]
        self._keys = [k for k, _, _ in specs]
        self.segment = SegmentedControl(specs)
        self.segment.changed.connect(self._on_section)
        # Section switcher, the active section's search, and its exports all
        # on ONE row.
        segrow = QHBoxLayout()
        segrow.setSpacing(10)
        segrow.addWidget(self.segment)
        self._search_host = QHBoxLayout()
        self._search_host.setContentsMargins(0, 0, 0, 0)
        segrow.addLayout(self._search_host, 1)
        self._export_host = QHBoxLayout()
        self._export_host.setContentsMargins(0, 0, 0, 0)
        self._export_host.setSpacing(9)
        segrow.addLayout(self._export_host)
        root.addWidget(design.toolbar_wrap(segrow))

        self.stack = QStackedWidget()
        for panel in (self.bank_panel, self.recv_panel, self.pay_panel):
            self.stack.addWidget(panel)
        root.addWidget(self.stack, 1)

        self._mount_tools()
        self.refresh()

    def _on_section(self, key: str) -> None:
        self.stack.setCurrentIndex(self._keys.index(key))
        self._mount_tools()

    def _mount_tools(self) -> None:
        """Show the CURRENT section's search + export in the shared top row."""
        for host in (self._search_host, self._export_host):
            while host.count():
                item = host.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
        panel = self.stack.currentWidget()
        if panel is None:
            return
        self._search_host.addWidget(panel.search)
        for b in panel.export_btns:
            self._export_host.addWidget(b)
        # Deliberately NOT advertising a _report_builder on the page: doing so
        # made the shared page-bar show its OWN Export PDF/Excel as well, so
        # the screen carried two identical pairs. The section's buttons live
        # in this toolbar, beside the section switcher.
        self._report_builder = None
        self._report_name = f"position_{panel.section}"

    def refresh(self) -> None:
        with SessionLocal() as session:
            pos = financial_position(session)
        for panel in (self.bank_panel, self.recv_panel, self.pay_panel):
            panel.update_data(pos)
        self._fill_summary(pos)

    def _fill_summary(self, pos) -> None:
        """Headline figures, from the SAME position object the panels use —
        no extra queries."""
        def fmt(v):
            return f"{float(v):,.2f}"

        # payable is already negative under the app-wide sign rule
        net = float(pos.grand_total) + float(pos.total_receivable) + float(pos.total_payable)
        self.tile_available.setText(fmt(pos.grand_total))
        self.tile_receivable.setText(fmt(pos.total_receivable))
        self.tile_payable.setText(fmt(pos.total_payable))
        self.tile_cheques.setText(fmt(pos.cheque_total))
        self.tile_net.setText(fmt(net))
        # Net worth turns red if the business is underwater.
        self.tile_net.setStyleSheet(
            f"color:{design.amt_color(net)};font-size:21px;font-weight:800;")
