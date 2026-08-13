"""Small helpers for building read-only ledger tables."""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QProgressBar,
    QStyle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from timber import i18n
from timber.ui import icons


class _ReadableSelectionDelegate(QStyledItemDelegate):
    """Keeps a selected row's text readable. On selection we paint every cell's
    text in the selection's own text color instead of the cell's own
    foreground — otherwise colored money cells (red / green / grey) keep their
    color and vanish against the selection background. The ForegroundRole only
    affects the Text role, so overriding Text + HighlightedText here wins."""

    def initStyleOption(self, option, index):  # noqa: N802 (Qt signature)
        super().initStyleOption(option, index)
        if option.state & QStyle.StateFlag.State_Selected:
            from timber.ui import design
            col = QColor(design.c("sel_text"))
            option.palette.setColor(QPalette.ColorRole.Text, col)
            option.palette.setColor(QPalette.ColorRole.HighlightedText, col)


def make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.Stretch
    )
    table.setShowGrid(False)          # the row separators carry the structure
    table.verticalHeader().setDefaultSectionSize(38)
    from timber.ui import design
    design.refresh()
    table.setStyleSheet(design.table_style())
    # Lock the selection colors at the PALETTE level too (not just the
    # stylesheet, which Qt does not always honor for selected cells), and use a
    # delegate so selected text stays readable over any per-cell color.
    pal = table.palette()
    pal.setColor(QPalette.ColorRole.Highlight, QColor(design.c("sel_row")))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(design.c("sel_text")))
    table.setPalette(pal)
    table.setItemDelegate(_ReadableSelectionDelegate(table))
    return table


def _show_empty(table: QTableWidget) -> None:
    """One centered, muted 'No records' row spanning the whole table — so an
    empty list reads as intentional instead of looking broken/blank."""
    from timber.ui import design
    ncol = max(1, table.columnCount())
    table.setRowCount(1)
    item = QTableWidgetItem(i18n.tr("no_records"))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setForeground(QBrush(QColor(design.c("muted"))))
    item.setFlags(Qt.ItemFlag.ItemIsEnabled)   # visible but not selectable
    table.setItem(0, 0, item)
    table.setSpan(0, 0, 1, ncol)
    table.setRowHeight(0, 88)


def fill_table(table: QTableWidget, rows: list[list], autosize: bool = False) -> None:
    """Populate a table. With ``autosize`` the row heights are computed here.

    Sizing rows used to mean a second pass — ``resizeRowsToContents`` re-laid
    out every cell (1.3s for 3000 rows, on every refresh). We are already
    walking every cell's text to build the items, so the tallest cell per row
    can be worked out in the same pass for almost nothing.
    """
    from timber.core.translate import tr_data

    _RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    # Repaint ONCE at the end, not on every cell — a Stretch header otherwise
    # recomputes column widths per row, which makes big tables crawl.
    table.setUpdatesEnabled(False)
    was_sorting = table.isSortingEnabled()
    if was_sorting:
        table.setSortingEnabled(False)

    fm = line_h = None
    wrap_widths: dict[int, int] = {}
    heights: list[int] = []
    if autosize:
        fm = table.fontMetrics()
        line_h = fm.lineSpacing()
        hdr = table.horizontalHeader()
        # Only pinned columns can wrap unpredictably; stretch columns grow.
        wrap_widths = {
            c: max(20, table.columnWidth(c) - 12)
            for c in range(table.columnCount())
            if hdr.sectionResizeMode(c) == QHeaderView.ResizeMode.Fixed
        }

    try:
        table.clearSpans()          # drop any previous empty-state span
        if not rows:
            _show_empty(table)
            return
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            lines = 1
            for c, value in enumerate(row):
                is_number = isinstance(value, (int, float, Decimal))
                text = str(value)
                shown = text if is_number else tr_data(text)
                item = QTableWidgetItem(shown)
                # Keep the original (English) text searchable even when the
                # cell is shown translated.
                if shown != text:
                    item.setData(Qt.ItemDataRole.UserRole, text)
                if is_number:
                    item.setTextAlignment(_RIGHT)
                table.setItem(r, c, item)

                if autosize and shown:
                    width = wrap_widths.get(c)
                    if width is None:
                        n = shown.count("\n") + 1
                    else:
                        n = 0
                        for seg in shown.split("\n"):
                            adv = fm.horizontalAdvance(seg)
                            n += 1 if adv <= width else -(-adv // width)
                        n = max(1, n)
                    if n > lines:
                        lines = n
            if autosize:
                heights.append(38 if lines <= 1 else lines * line_h + 12)

        for r, h in enumerate(heights):
            table.setRowHeight(r, h)
    finally:
        if was_sorting:
            table.setSortingEnabled(True)
        table.setUpdatesEnabled(True)


def fmt(value: Decimal | float | int) -> str:
    """Format money/quantities with thousands separators, 2 dp."""
    return f"{value:,.2f}"


# Balance colours. THE universal rule across the whole app: money we must
# GIVE shows negative (red); money we will RECEIVE shows positive (green).
BAL_RED = "#c62828"     # negative — we must give
BAL_GREEN = "#16a34a"   # positive — we will receive
BAL_GREY = "#64748b"    # settled


def bal_value(is_supplier: bool, internal_balance) -> Decimal:
    """Convert a party's INTERNAL 'what we owe' balance into the display value
    under the universal rule (give = negative, receive = positive).

    - Supplier: internal>0 means we owe them (give)   -> negative.
    - Factory:  internal>0 means they owe us (receive) -> positive.
    """
    d = Decimal(str(internal_balance))
    return -d if is_supplier else d


def bal_text(is_supplier: bool, internal_balance) -> str:
    return fmt(bal_value(is_supplier, internal_balance))


def bal_colour(is_supplier: bool, internal_balance) -> str:
    d = bal_value(is_supplier, internal_balance)
    if d < 0:
        return BAL_RED
    if d > 0:
        return BAL_GREEN
    return BAL_GREY


def words_label() -> QLabel:
    """A faint, italic label that shows an amount spelled out in words."""
    lbl = QLabel("")
    lbl.setStyleSheet("color: gray; font-style: italic; font-size: 11px;")
    lbl.setWordWrap(True)
    return lbl


def attach_words(spin, label: QLabel) -> None:
    """Live-update ``label`` with the spin's value in words as you type."""
    from timber.core.num_to_words import to_words

    def _update() -> None:
        label.setText(to_words(spin.value()) if spin.value() else "")

    spin.valueChanged.connect(_update)
    _update()


def stacked_cell(items: list[str]) -> QWidget:
    """A table cell that stacks multiple values vertically, each split by
    a thin divider line (used for multiple phones / bank accounts)."""
    widget = QWidget()
    widget.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(5)
    # Honour each label's natural height so rows never clip the content.
    layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
    cleaned = [t for t in items if t]
    if not cleaned:
        layout.addWidget(QLabel(""))
        return widget
    for idx, text in enumerate(cleaned):
        if idx > 0:
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFixedHeight(1)
            line.setStyleSheet("color: #cbd5e1; background: #cbd5e1;")
            layout.addWidget(line)
        label = QLabel(text)
        label.setWordWrap(False)  # keep "IBAN: <value>" on one line
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
    return widget


def stat_card(title: str, value: str, colour: str, subtitle: str = "",
              icon_name: str = "") -> QFrame:
    """A KPI card for the ledger / summary pages.

    Thin wrapper over the ONE shared tile (``design.stat_tile``) so the ledgers
    look pixel-identical to the Dashboard / Reports tiles (compact size, vivid
    gradient icon chip). ``colour`` is the accent; the value stays in the normal
    text colour (ledger figures are neutral, not signed). The optional
    ``subtitle`` is appended below — the one thing stat_tile has no slot for.
    The signature is unchanged so every existing call site still works.
    """
    from timber.ui import design

    frame, _val = design.stat_tile(
        title, colour, icon_name, value=value, value_color=design.c("text"))
    if subtitle:
        s = QLabel(subtitle)
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{design.c('muted')};font-size:11px;")
        frame.layout().addWidget(s)
    return frame


def card_strip(cards: list[QFrame]) -> QHBoxLayout:
    """Lay KPI cards out in an evenly-spaced horizontal row."""
    row = QHBoxLayout()
    row.setSpacing(14)
    for c in cards:
        row.addWidget(c, stretch=1)
    return row


def autosize_rows(table: QTableWidget, base: int = 38, pad: int = 12) -> None:
    """Size rows to their tallest cell without Qt's per-row layout pass.

    ``QTableWidget.resizeRowsToContents`` re-lays out every cell of every row
    through the item delegate. On a word-wrapped, stretch-header table that was
    ~1.3s for 3000 rows — half the Trades page's open time — and it ran again
    on every refresh. Measuring the text ourselves with the font metrics gives
    the same heights in a few milliseconds.

    Only columns with an explicitly fixed width can wrap in a way we cannot
    predict from newlines, so those are the only ones measured properly.
    """
    fm = table.fontMetrics()
    line_h = fm.lineSpacing()
    hdr = table.horizontalHeader()
    # Columns the layout has pinned: these wrap, so they need real measuring.
    fixed = [c for c in range(table.columnCount())
             if hdr.sectionResizeMode(c) == QHeaderView.ResizeMode.Fixed]
    widths = {c: max(20, table.columnWidth(c) - 12) for c in fixed}

    # The wrapping columns hold generated text ("2,500.00 (us)" and friends),
    # so the same string recurs on hundreds of rows. Measuring each distinct
    # string once turns thousands of layout calls into a few dozen.
    measured: dict[tuple[int, str], int] = {}

    for r in range(table.rowCount()):
        lines = 1
        for c in range(table.columnCount()):
            item = table.item(r, c)
            if item is None:
                continue
            text = item.text()
            if not text:
                continue
            n = text.count("\n") + 1
            if c in widths:
                key = (c, text)
                cached = measured.get(key)
                if cached is None:
                    rect = fm.boundingRect(
                        0, 0, widths[c], 0,
                        int(Qt.TextFlag.TextWordWrap), text)
                    # Ceiling, not floor: a partly-filled last line still
                    # needs a whole line of height or the text clips.
                    cached = max(1, -(-rect.height() // line_h))
                    measured[key] = cached
                if cached > n:
                    n = cached
            if n > lines:
                lines = n
        table.setRowHeight(r, base if lines <= 1 else lines * line_h + pad)


def hide_empty_columns(table: QTableWidget, cols: list[int]) -> None:
    """Hide each given column if every row's cell in it is empty; show it
    otherwise. Call after the table is filled (re-evaluated each refresh)."""
    for c in cols:
        has_data = False
        for r in range(table.rowCount()):
            item = table.item(r, c)
            if item is not None and item.text().strip():
                has_data = True
                break
        table.setColumnHidden(c, not has_data)


def colour_cell(table: QTableWidget, row: int, col: int, colour: str) -> None:
    """Tint one cell's text (used to flag debit/credit/overdue values)."""
    item = table.item(row, col)
    if item is not None:
        item.setForeground(QColor(colour))


def progress_cell(percent: float) -> QProgressBar:
    """A thin progress bar (0-100) showing how much of a load is paid.
    Green once fully paid, blue while partially paid, grey at zero."""
    pct = max(0, min(100, int(round(percent))))
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(pct)
    bar.setFormat(f"{pct}%")
    bar.setTextVisible(True)
    bar.setFixedHeight(18)
    if pct >= 100:
        chunk = "#16a34a"   # green - fully paid
    elif pct > 0:
        chunk = "#2563eb"   # blue - partially paid
    else:
        chunk = "#cbd5e1"   # grey - nothing paid yet
    bar.setStyleSheet(
        "QProgressBar {"
        " border: 1px solid #cbd5e1; border-radius: 6px;"
        " background: #f1f5f9; text-align: center;"
        " font-size: 11px; font-weight: 600; color: #0f172a; }"
        f" QProgressBar::chunk {{ background: {chunk}; border-radius: 5px; }}"
    )
    return bar


def filter_table(table: QTableWidget, text: str) -> None:
    """Hide rows of ``table`` that don't contain ``text`` (any column)."""
    text = (text or "").strip().lower()
    for r in range(table.rowCount()):
        if not text:
            table.setRowHidden(r, False)
            continue
        match = False
        for c in range(table.columnCount()):
            item = table.item(r, c)
            if item is not None and text in item.text().lower():
                match = True
                break
        table.setRowHidden(r, not match)


class SearchBox(QLineEdit):
    """A live filter for a table: hides rows that don't match the text.

    Call ``apply()`` after repopulating the table to keep the filter
    active across refreshes.
    """

    def __init__(self, table: QTableWidget, parent=None) -> None:
        super().__init__(parent)
        self._table = table
        self.setPlaceholderText(i18n.tr("search"))
        self.setClearButtonEnabled(True)
        from timber.ui import design
        design.refresh()
        self.setStyleSheet(design.input_style())
        self.setMinimumWidth(220)
        try:
            self.addAction(icons.icon("search", design.c("muted"), 15),
                           QLineEdit.ActionPosition.LeadingPosition)
        except Exception:  # noqa: BLE001 - decoration only
            pass
        self.textChanged.connect(self.apply)

    def apply(self) -> None:
        text = self.text().strip().lower()
        table = self._table
        for r in range(table.rowCount()):
            if not text:
                table.setRowHidden(r, False)
                continue
            match = False
            for c in range(table.columnCount()):
                item = table.item(r, c)
                if item is None:
                    continue
                # Match the visible text and any hidden search text
                # (used when a cell shows a custom widget instead).
                hidden = item.data(Qt.ItemDataRole.UserRole)
                haystack = f"{item.text()} {hidden or ''}".lower()
                if text in haystack:
                    match = True
                    break
            table.setRowHidden(r, not match)
