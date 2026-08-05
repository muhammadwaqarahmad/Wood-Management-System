"""A combo box you can type into to filter its list.

Click the field to see the whole list, or start typing to shrink it to
matching names (match-anywhere, case-insensitive, Urdu or English). A
completer popup does the filtering, so the text field keeps focus the whole
time — you can click to open AND immediately type to narrow. Nothing is
auto-selected on load, so a stray keystroke can never silently record the
wrong supplier/factory.

``currentData()`` / ``currentIndex()`` stay correct, so call sites use it like
a normal ``QComboBox``: ``addItem(name, id)``, ``currentData()``, etc.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QCompleter


def style_completer_popup(completer: QCompleter) -> None:
    """Paint a completer's popup from the active palette.

    The popup is a TOP-LEVEL view, not a child of the combo, so the app-wide
    ``QComboBox QAbstractItemView`` rule never reached it: it kept the system's
    white background while the global rule made the text light. In dark mode
    that was light-on-white — effectively invisible.
    """
    from timber.ui import theme

    p = theme.palette()
    popup = completer.popup()
    if popup is None:
        return
    popup.setStyleSheet(
        f"background:{p['input_bg']};"
        f"color:{p['text']};"
        f"border:1px solid {p['border']};"
        "border-radius:8px;"
        "outline:0;"
        f"selection-background-color:{p['accent']};"
        "selection-color:#ffffff;"
    )


class SearchableComboBox(QComboBox):
    def __init__(self, placeholder: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(16)
        # Do NOT let the longest item dictate the widget's width. A combo
        # sizes to its widest entry by default, and party names here run to
        # ~40 characters — that dragged whole dialogs out past their own
        # edges and pushed the left-hand labels off screen. The popup still
        # shows names in full; only the closed box is constrained.
        self.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.setMinimumContentsLength(12)
        line = self.lineEdit()
        line.setClearButtonEnabled(True)
        if placeholder:
            line.setPlaceholderText(placeholder)

        # The completer popup keeps the text field focused, so the user can
        # type to filter while it's open (unlike the combo's own popup, which
        # would steal the keyboard). Match anywhere, ignore case.
        comp = QCompleter(self.model(), self)
        comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setCompletionRole(Qt.ItemDataRole.DisplayRole)
        self.setCompleter(comp)
        self._completer = comp
        style_completer_popup(comp)
        self.setCurrentIndex(-1)  # no auto-select

        line.installEventFilter(self)
        comp.activated[str].connect(self._select_by_text)
        line.editingFinished.connect(self._commit_exact)

    def _select_by_text(self, text: str) -> None:
        idx = self.findText(text, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def _commit_exact(self) -> None:
        """Focus left the field: keep the shown text and the real selection
        consistent. An empty field means 'no party'; free text that isn't an
        exact item snaps back to the last valid choice."""
        text = self.lineEdit().text().strip()
        if not text:
            if self.currentIndex() != -1:
                self.setCurrentIndex(-1)
            return
        idx = self.findText(text, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            cur = self.currentIndex()
            self.lineEdit().setText(self.itemText(cur) if cur >= 0 else "")

    def _show_all(self) -> None:
        # Show the entire list (empty prefix) with the field still focused.
        # Re-style first: the theme may have changed since this widget was
        # built, and the popup is recreated by Qt behind our back.
        style_completer_popup(self._completer)
        self._completer.setCompletionPrefix("")
        self._completer.complete()

    def eventFilter(self, obj, event):  # noqa: N802 (Qt override)
        if obj is self.lineEdit():
            etype = event.type()
            # Clicking into the field selects its text, so the first keystroke
            # replaces the old name instead of appending to it.
            if etype == QEvent.Type.FocusIn:
                QTimer.singleShot(0, self.lineEdit().selectAll)
            # Clicking the field drops the whole list open — same feel as the
            # web Buy & Sell page — and the field keeps focus so the user can
            # type straight away to filter.
            elif etype == QEvent.Type.MouseButtonPress:
                QTimer.singleShot(0, self._show_all)
        return super().eventFilter(obj, event)
