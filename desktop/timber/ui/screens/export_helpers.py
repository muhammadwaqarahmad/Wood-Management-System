"""Shared export buttons / save dialogs for the report screens.

Screens call :func:`export_buttons` as before; it now also *registers* the
report builder on the screen so a shared page toolbar (in the main window)
can drive the same PDF / Excel export from one place.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QWidget

from timber.ui.toast import err_toast, info_toast, warn_toast
from timber import i18n
from timber.core.report_data import ReportData


def run_export(parent: QWidget, build: Callable[[], ReportData], default_name: str,
               fmt: str) -> None:
    """Build the report fresh and save it as ``fmt`` ('pdf' or 'xlsx')."""
    # Imported HERE, not at module top: reportlab (PDF) and openpyxl (Excel)
    # together pull in ~250 modules and add seconds to startup, but are only
    # needed the moment someone actually exports. Loading them on the button
    # click keeps every launch fast for the majority who never export.
    from timber.core import excel_export, pdf_export

    if fmt == "xlsx":
        writer, suffix, file_filter, title_key = (
            excel_export, "xlsx", "Excel (*.xlsx)", "export_excel")
    else:
        writer, suffix, file_filter, title_key = (
            pdf_export, "pdf", "PDF (*.pdf)", "export_pdf")
    path, _ = QFileDialog.getSaveFileName(
        parent, i18n.tr(title_key), f"{default_name}.{suffix}", file_filter
    )
    if not path:
        return
    try:
        report = build()
        writer.write(report, path)
    except Exception as exc:  # noqa: BLE001
        err_toast(parent, i18n.tr("error"), str(exc))
        return
    info_toast(parent, i18n.tr("exported"), path)


def export_buttons(
    parent: QWidget, build: Callable[[], ReportData], default_name: str,
    as_widgets: bool = False,
):
    """PDF + Excel export buttons. ``build`` returns the report fresh each
    click (so it reflects the current selection/data).

    Returns a right-aligned ``QHBoxLayout`` by default, or — with
    ``as_widgets=True`` — the ``[pdf_btn, xls_btn]`` list so a caller can drop
    them into its own toolbar. Either way it registers ``build`` on the screen
    (``_report_builder``) and remembers the buttons (``_export_btns``) so the
    shared page toolbar can take over."""
    from PySide6.QtCore import Qt

    from timber.ui import design, icons

    design.refresh()
    pdf_btn = QPushButton(i18n.tr("export_pdf"))
    pdf_btn.clicked.connect(lambda: run_export(parent, build, default_name, "pdf"))
    xls_btn = QPushButton(i18n.tr("export_excel"))
    xls_btn.clicked.connect(lambda: run_export(parent, build, default_name, "xlsx"))
    for b in (pdf_btn, xls_btn):
        b.setStyleSheet(design.btn("ghost"))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        try:
            b.setIcon(icons.icon("download", design.c("text"), 15))
        except Exception:  # noqa: BLE001 - decoration only
            pass

    if getattr(parent, "_report_builder", None) is None:
        parent._report_builder = build
        parent._report_name = default_name
    else:
        parent._report_multi = True  # more than one report on this screen
    parent._export_btns = getattr(parent, "_export_btns", []) + [pdf_btn, xls_btn]

    if as_widgets:
        return [pdf_btn, xls_btn]

    layout = QHBoxLayout()
    layout.setSpacing(9)
    layout.addStretch()
    layout.addWidget(pdf_btn)
    layout.addWidget(xls_btn)
    return layout
