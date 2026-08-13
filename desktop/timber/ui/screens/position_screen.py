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
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.ui import design, icons
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


def _kpi_card(title: str, value: str, accent: str, icon: str = "") -> QFrame:
    """A KPI tile — the shared ``design.stat_tile``, so the panel cards match
    the page headline and the Dashboard (one component, one look)."""
    from timber.ui import design

    frame, val = design.stat_tile(title, accent, icon)
    val.setText(value)
    frame.setMinimumHeight(78)
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
                               i18n.tr("to_receive"), BAL_GREEN, "trending-up")
        else:
            self._fill_parties(pos.payables, pos.total_payable,
                               i18n.tr("to_give"), BAL_RED, "trending-down")
        self.search.apply()

    def _fill_bank(self, pos) -> None:
        cards = [
            (i18n.tr("bank_total"), fmt(pos.bank_total), _ACCENT_BLUE, "landmark"),
            (i18n.tr("cash_position"), fmt(pos.cash_balance),
             _money_colour(pos.cash_balance), "wallet"),
            (i18n.tr("cheque_balance"), fmt(pos.cheque_total), _ACCENT_AMBER,
             "file-check"),
        ]
        # Unattributed money is already inside the grand total; show it as its
        # own card only when there is some waiting to be claimed.
        if pos.unclaimed_total > 0:
            cards.append(
                (i18n.tr("unclaimed_total"), fmt(pos.unclaimed_total),
                 _ACCENT_AMBER, "info")
            )
        cards.append(
            (i18n.tr("grand_total"), fmt(pos.grand_total),
             _money_colour(pos.grand_total), "pie-chart")
        )
        for title, value, accent, icon in cards:
            self.cards_layout.addWidget(_kpi_card(title, value, accent, icon))
        fill_table(self.table, [
            [a.name, a.bank_name or "", fmt(a.closing)] for a in pos.accounts
        ])
        for i, a in enumerate(pos.accounts):
            colour_cell(self.table, i, 2, _money_colour(a.closing))

    def _fill_parties(self, rows, total, label, accent, icon="") -> None:
        self.cards_layout.addWidget(_kpi_card(label, fmt(total), accent, icon))
        self.cards_layout.addWidget(
            _kpi_card(i18n.tr("parties"), str(len(rows)), _ACCENT_SLATE, "book-user")
        )
        self.cards_layout.addStretch()
        fill_table(self.table, [
            [r.name, r.contact, i18n.tr(_kind_key(r.kind)), fmt(r.amount)]
            for r in rows
        ])
        for i in range(len(rows)):
            colour_cell(self.table, i, 3, accent)


class _PositionExportDialog(design.Dialog):
    """Pick which sections to export: Bank / To receive / To give."""

    def __init__(self, current_section, parent=None) -> None:
        super().__init__(i18n.tr("export"), "download", parent=parent, width=420)
        self.fmt = "pdf"
        hint = QLabel(i18n.tr("export_choose_sections"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{design.c('muted')};font-size:12px;")
        self.body.addWidget(hint)

        self.cb_bank = QCheckBox(i18n.tr("bank_total"))
        self.cb_recv = QCheckBox(i18n.tr("to_receive"))
        self.cb_pay = QCheckBox(i18n.tr("to_give"))
        self.cb_bank.setChecked(current_section == "bank")
        self.cb_recv.setChecked(current_section == "receivable")
        self.cb_pay.setChecked(current_section == "payable")
        for cb in (self.cb_bank, self.cb_recv, self.cb_pay):
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            self.body.addWidget(cb)

        pdf, _cancel = self.buttons(i18n.tr("export_pdf"))
        pdf.clicked.connect(lambda: self._go("pdf"))
        xls = QPushButton(i18n.tr("export_excel"))
        xls.setStyleSheet(design.btn("primary"))
        xls.setCursor(Qt.CursorShape.PointingHandCursor)
        xls.clicked.connect(lambda: self._go("xlsx"))
        self.add_button(xls)

    def _go(self, fmt: str) -> None:
        if not self.selection():
            return
        self.fmt = fmt
        self.accept()

    def selection(self) -> set:
        sel = set()
        if self.cb_bank.isChecked():
            sel.add("bank")
        if self.cb_recv.isChecked():
            sel.add("receivable")
        if self.cb_pay.isChecked():
            sel.add("payable")
        return sel


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
        # One selectable export (Bank / To receive / To give), like the Reports
        # page — receivable + payable together use the same two-column list form.
        self.export_btn = QPushButton(i18n.tr("export"))
        self.export_btn.setStyleSheet(design.btn("primary"))
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        try:
            self.export_btn.setIcon(icons.icon("download", "#ffffff", 15))
        except Exception:  # noqa: BLE001 - icon is decoration only
            pass
        self.export_btn.clicked.connect(self._open_export)
        segrow.addWidget(self.export_btn)
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
        """Show the CURRENT section's search in the shared top row. Export is a
        single selectable button (not per-section), so nothing to mount here."""
        while self._search_host.count():
            item = self._search_host.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        panel = self.stack.currentWidget()
        if panel is None:
            return
        self._search_host.addWidget(panel.search)
        # No shared top-right export — the page's own "Export" button drives it.
        self._report_builder = None

    def _open_export(self) -> None:
        """Pick sections (Bank / To receive / To give) and export one file."""
        from timber.core.report_data import financial_position_report
        from timber.ui.screens.export_helpers import run_export

        panel = self.stack.currentWidget()
        section = panel.section if panel else "bank"
        dlg = _PositionExportDialog(section, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sel = dlg.selection()
        if not sel:
            return

        def _build():
            with SessionLocal() as s:
                return financial_position_report(s, sel)

        run_export(self, _build, "financial_position", dlg.fmt)

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
