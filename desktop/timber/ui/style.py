"""Global application stylesheet (QSS) for a modern, consistent look."""

APP_STYLESHEET = """
* {
    font-family: 'Segoe UI', 'Tahoma', sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog { background: #eef2f8; }

/* ---- Header bar ---- */
QFrame#header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1e3a8a, stop:1 #2563eb);
    border: none;
}
QLabel#headerTitle { color: white; font-size: 18px; font-weight: bold; }
QLabel#headerUser  { color: #d6e4ff; font-size: 12px; }

QPushButton#logout {
    background: rgba(255,255,255,0.18);
    color: white;
    border-radius: 8px;
    padding: 7px 16px;
    font-weight: 600;
}
QPushButton#logout:hover { background: rgba(255,255,255,0.32); }

/* ---- Sidebar nav ---- */
QListWidget#nav {
    background: #0f2440;
    border: none;
    outline: 0;
    padding: 8px 6px;
}
QListWidget#nav::item {
    color: #cfddf2;
    padding: 9px 12px;
    margin: 2px 4px;
    border-radius: 8px;
}
QListWidget#nav::item:hover    { background: #1b3a63; }
QListWidget#nav::item:selected { background: #2563eb; color: white; }
QListWidget#nav::item:disabled {
    color: #6f8bb3;
    font-size: 11px;
    margin-top: 8px;
    background: transparent;
}

/* ---- Buttons ---- */
QPushButton {
    background: #2563eb;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
}
QPushButton:hover    { background: #1d4ed8; }
QPushButton:pressed  { background: #1e40af; }
QPushButton:disabled { background: #aebfdf; color: #f0f4ff; }

/* ---- Inputs ---- */
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit, QPlainTextEdit {
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 8px;
    background: white;
    selection-background-color: #2563eb;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus,
QSpinBox:focus, QDateEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #2563eb;
}
QComboBox::drop-down { border: none; width: 22px; }

/* ---- Tables ---- */
QTableWidget {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    gridline-color: #eef2f7;
}
QHeaderView::section {
    background: #e8effb;
    color: #1e293b;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #d3deef;
    font-weight: 600;
}
QTableWidget::item { padding: 4px; }
QTableWidget::item:selected { background: #dbe7ff; color: #0f2440; }

/* ---- Tabs ---- */
QTabWidget::pane { border: 1px solid #e2e8f0; border-radius: 8px; top: -1px; background: white; }
QTabBar::tab {
    background: #e3eaf5;
    color: #334155;
    padding: 8px 22px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 3px;
    font-weight: 600;
}
QTabBar::tab:selected { background: #2563eb; color: white; }
QTabBar::tab:hover:!selected { background: #cdd9ee; }

/* ---- Misc surfaces ---- */
QScrollArea { border: none; background: transparent; }
QPlainTextEdit { font-family: 'Consolas', monospace; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #b9c6db; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #94a8c6; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
