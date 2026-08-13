"""Theming: Light / Dark palettes + a QSS builder.

The active theme is persisted per-PC via ``app_settings`` (like the
language) and applied app-wide with ``QApplication.setStyleSheet``.
"""

from __future__ import annotations

from string import Template

from timber.core import app_settings

THEMES = {"light": "Light", "dark": "Dark"}

_current: str | None = None


def get_theme() -> str:
    global _current
    if _current is None:
        t = app_settings.get("theme", "light")
        _current = t if t in _PALETTES else "light"
    return _current


def set_theme(theme: str) -> None:
    global _current
    if theme not in _PALETTES:
        raise ValueError(f"Unknown theme: {theme!r}")
    _current = theme
    app_settings.set("theme", theme)


_PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "window": "#eef2f8", "surface": "#ffffff", "text": "#1e293b",
        "muted": "#64748b", "border": "#e2e8f0",
        "primary": "#2563eb", "primary_hover": "#1d4ed8",
        "primary_pressed": "#1e40af", "primary_disabled": "#aebfdf",
        "sidebar_bg": "#0f1729", "sidebar_bg2": "#0b1120",
        "sidebar_text": "#c7d2e4", "sidebar_hover": "rgba(255,255,255,0.06)",
        "sidebar_section": "#5f6f8c", "sidebar_border": "#0b1120",
        "menu_bg": "#ffffff", "menu_border": "#e2e8f0", "menu_text": "#1e293b",
        "menu_hover": "#f1f5f9",
        "chip_hover": "rgba(255,255,255,0.16)",
        "accent": "#6366f1", "accent2": "#a855f7",
        "header_main": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #a855f7)",
        "header_user": "#e0e7ff", "header_border": "rgba(255,255,255,0.16)",
        "th_bg": "#e8effb", "th_text": "#1e293b",
        "alt_row": "#f5f8ff", "sel_row": "#dbe7ff", "sel_text": "#0f2440",
        "input_bg": "#ffffff", "input_border": "#cbd5e1",
        "tab_bg": "#e3eaf5", "tab_text": "#334155", "tab_hover": "#cdd9ee",
        "scroll": "#b9c6db", "scroll_hover": "#94a8c6",
    },
    "dark": {
        "window": "#0f172a", "surface": "#1e293b", "text": "#e2e8f0",
        "muted": "#94a3b8", "border": "#334155",
        "primary": "#3b82f6", "primary_hover": "#2563eb",
        "primary_pressed": "#1d4ed8", "primary_disabled": "#475569",
        "sidebar_bg": "#0a0f1c", "sidebar_bg2": "#070b14",
        "sidebar_text": "#cbd5e1", "sidebar_hover": "rgba(255,255,255,0.05)",
        "sidebar_section": "#64748b", "sidebar_border": "#070b14",
        "menu_bg": "#1e293b", "menu_border": "#334155", "menu_text": "#e2e8f0",
        "menu_hover": "#334155",
        "chip_hover": "rgba(255,255,255,0.14)",
        "accent": "#6366f1", "accent2": "#a855f7",
        "header_main": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #9333ea)",
        "header_user": "#ddd6fe", "header_border": "rgba(255,255,255,0.10)",
        "th_bg": "#243049", "th_text": "#e2e8f0",
        "alt_row": "#1b2536", "sel_row": "#1d4ed8", "sel_text": "#ffffff",
        "input_bg": "#0f172a", "input_border": "#475569",
        "tab_bg": "#243049", "tab_text": "#cbd5e1", "tab_hover": "#334155",
        "scroll": "#475569", "scroll_hover": "#64748b",
    },
}

_TEMPLATE = Template(
    """
* { font-family: 'Segoe UI', 'Tahoma', sans-serif; font-size: 13px; color: $text; }

QMainWindow, QDialog { background: $window; }
/* A QScrollArea's viewport paints its OWN opaque background (white by default),
   which showed as a pale band behind scrolling content on the dark theme. Make
   the viewport and the widget inside it transparent so the page surface shows. */
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* Confirmation / info / error popups. Anything routed through timber.ui.design
   gets the full treatment; this keeps a stray native QMessageBox in family. */
QMessageBox { background: $surface; }
QMessageBox QLabel { color: $text; font-size: 14px; min-width: 280px; padding: 6px 8px; }
QMessageBox QPushButton { min-width: 100px; padding: 9px 20px; margin: 3px; }

/* Dialog chrome shared by every add / edit / confirm box (timber.ui.design). */
QFrame#dlgHead, QFrame#dlgFoot { border-left: none; border-right: none; }
QDialog QLabel { color: $text; }

/* Floating content panel that holds the active screen — borderless for a clean
   edge (the surface/window contrast already separates it from the page). */
QStackedWidget#content { background: $surface; border: none; border-radius: 14px; }

/* Top header — a dark brand block over the sidebar, a light bar over content */
QFrame#header { background: transparent; border: none; }
QFrame#brandBox {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $sidebar_bg, stop:1 $sidebar_bg);
    border: none; border-right: 1px solid $sidebar_border;
    border-bottom: 1px solid rgba(255,255,255,0.14);
}
QFrame#headerMain { background: $header_main; border-bottom: 1px solid $header_border; }
QLabel#headerBrand { color: white; font-size: 15px; font-weight: 800; letter-spacing: 0.2px; }
QToolButton#menuToggle { background: transparent; border: none; border-radius: 9px; padding: 7px; }
QToolButton#menuToggle:hover { background: rgba(255,255,255,0.12); }

/* Shared page bar in the gap above the content card: title + export */
QFrame#pageBar { background: transparent; border: none; }
QLabel#pageTitle { color: $text; font-size: 23px; font-weight: 800; letter-spacing: 0.2px;
                   padding: 2px 0 2px 2px; }
QToolButton#bell { background: transparent; border: none; border-radius: 9px; padding: 7px; }
QToolButton#bell:hover { background: $chip_hover; }
QFrame#headerDivider { background: rgba(255,255,255,0.35); border: none; }

/* Header profile button — just the avatar, with a soft round hover halo */
QFrame#userChip { background: transparent; border: none; border-radius: 22px; }
QFrame#userChip:hover { background: $chip_hover; }
QLabel#avatar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $accent, stop:1 $accent2);
    color: white; border-radius: 18px; font-size: 13px; font-weight: 700;
}
/* On the gradient header the avatar shares the accent hue, so ring it in
   white to make it pop. (The dropdown-menu avatar stays plain.) */
QFrame#userChip QLabel#avatar { border: 2px solid rgba(255,255,255,0.75); }

/* Dropdown menu (user header + Account / Logout) */
QMenu#userMenu {
    background: $menu_bg; border: 1px solid $menu_border; border-radius: 12px;
    padding: 6px;
}
QWidget#menuHeader { background: transparent; }
QLabel#menuName { color: $text; font-size: 13px; font-weight: 700; }
QLabel#menuRole { color: $muted; font-size: 11px; }
QMenu#userMenu::item {
    color: $menu_text; padding: 9px 30px 9px 14px; border-radius: 8px; margin: 1px 2px;
    font-size: 13px; font-weight: 600;
}
QMenu#userMenu::item:selected { background: $menu_hover; }
QMenu#userMenu::icon { padding-left: 10px; }
QMenu#userMenu::separator { height: 1px; background: $menu_border; margin: 5px 8px; }

/* Generic dropdown menus (the sub-ledger "Manage" menu, context menus, etc.)
   — without this a plain QMenu falls back to a white OS box with unreadable
   text on the dark theme. */
QMenu {
    background: $menu_bg; color: $menu_text;
    border: 1px solid $menu_border; border-radius: 10px; padding: 5px;
}
QMenu::item {
    color: $menu_text; padding: 8px 22px 8px 14px;
    border-radius: 7px; margin: 1px 2px; font-weight: 600;
}
QMenu::item:selected { background: $menu_hover; color: $text; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $menu_border; margin: 4px 8px; }

/* Sidebar — dark panel with icon navigation */
QWidget#sidebar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $sidebar_bg, stop:1 $sidebar_bg2);
    border: none; border-right: 1px solid $sidebar_border;
}
QTreeWidget#nav {
    background: transparent; border: none; outline: 0; padding: 10px 8px;
    show-decoration-selected: 0;  /* never paint selection in the indent strip */
}
QTreeWidget#nav::item {
    color: $sidebar_text; padding: 8px 10px; margin: 1px 0;
    border-radius: 9px; border-left: 3px solid transparent;
}
QTreeWidget#nav::item:hover { background: $sidebar_hover; color: white; }
QTreeWidget#nav::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent2);
    color: white; font-weight: 700;
    border-left: 3px solid rgba(255,255,255,0.75);
}
/* The indent/branch strip must never paint the selection (no box left of
   the pill). */
QTreeWidget#nav::branch,
QTreeWidget#nav::branch:selected,
QTreeWidget#nav::branch:hover {
    background: transparent; image: none; border-image: none;
}

/* Default button = the accent gradient used by design.btn("primary"), so a
   plain QPushButton anywhere already matches the redesigned pages. */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $accent2, stop:1 $accent);
    color: white; border: none;
    border-radius: 9px; padding: 9px 20px; font-weight: 700;
}
QPushButton:hover    { background: $accent; }
QPushButton:pressed  { background: $primary_pressed; }
QPushButton:disabled { background: $primary_disabled; color: #f0f4ff; }

QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit, QPlainTextEdit, QListWidget {
    border: 1px solid $input_border; border-radius: 9px; padding: 8px 11px;
    background: $input_bg; color: $text; selection-background-color: $accent;
    min-height: 20px;
}
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover,
QDateEdit:hover { border-color: $accent; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus,
QDateEdit:focus, QPlainTextEdit:focus { border: 1px solid $accent; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: $input_bg; color: $text; border: 1px solid $border; border-radius: 8px;
    selection-background-color: $accent; selection-color: white;
}

QTableWidget {
    background: $surface; border: 1px solid $border; border-radius: 12px;
    gridline-color: $border; alternate-background-color: $alt_row;
}
QHeaderView::section {
    background: $th_bg; color: $th_text; padding: 11px 9px; border: none;
    border-bottom: 2px solid $border; font-weight: 700;
}
/* NO "QTableWidget::item" / "::item:selected" rules — a stylesheet ::item rule
   makes Qt shrink the SELECTED cell's text rect and elide ("...") numbers only
   while a row is selected. Selection colors come from the widget palette
   (Highlight / HighlightedText, set in table_utils.make_table) instead. */

QTabWidget::pane { border: 1px solid $border; border-radius: 8px; top: -1px; background: $surface; }
QTabBar::tab {
    background: $tab_bg; color: $tab_text; padding: 8px 22px;
    border-top-left-radius: 8px; border-top-right-radius: 8px;
    margin-right: 3px; font-weight: 600;
}
QTabBar::tab:selected { background: $primary; color: white; }
QTabBar::tab:hover:!selected { background: $tab_hover; }

QGroupBox { border: 1px solid $border; border-radius: 8px; margin-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: $muted; }

/* Floating scrollbars: the handle is inset from the panel edge (via margin)
   so it never collides with the rounded corner, and the track stays invisible. */
QScrollBar:vertical { background: transparent; width: 13px; margin: 6px 3px 6px 0; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 4px; min-height: 34px; }
QScrollBar::handle:vertical:hover { background: $scroll_hover; }
QScrollBar:horizontal { background: transparent; height: 13px; margin: 0 6px 3px 6px; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 4px; min-width: 34px; }
QScrollBar::handle:horizontal:hover { background: $scroll_hover; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* Sidebar scrollbar: slim and subtle on the light panel */
QTreeWidget#nav QScrollBar:vertical { width: 8px; background: transparent; margin: 0; }
QTreeWidget#nav QScrollBar::handle:vertical {
    background: rgba(100,116,139,0.28); border-radius: 4px; min-height: 30px;
}
QTreeWidget#nav QScrollBar::handle:vertical:hover { background: rgba(100,116,139,0.5); }

QChartView { background: $surface; border: 1px solid $border; border-radius: 8px; }
"""
)


def build_stylesheet(theme: str | None = None) -> str:
    return _TEMPLATE.substitute(_PALETTES[theme or get_theme()])


def palette(theme: str | None = None) -> dict[str, str]:
    """The active colour palette (light/dark) for building theme-aware widgets
    that style themselves with inline QSS (e.g. the Buy & Sell page)."""
    return dict(_PALETTES[theme or get_theme()])


def sidebar_icon_colors() -> tuple[str, str]:
    """(normal, selected) colours for sidebar nav icons in the active theme."""
    p = _PALETTES[get_theme()]
    return p["sidebar_text"], "#ffffff"


def header_icon_color() -> str:
    """Colour for icon buttons on the header bar (bell, hamburger)."""
    return "#ffffff"
