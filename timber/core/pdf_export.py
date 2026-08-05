"""Render a ReportData to a polished, branded PDF using ReportLab.

- Branded header (business name + report title + generated time).
- Footer with page numbers on every page.
- Wide reports auto-switch to landscape; font scales with column count.
- Full Urdu support: Arabic-script text is reshaped + bidi-reordered and
  drawn with a bundled Naskh font (no more dotted boxes).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from timber import config, i18n
from timber.core.pdf_fonts import has_rtl, register_fonts, shape
from timber.core.report_data import ReportData

_BRAND = colors.HexColor("#1565c0")
_BRAND_DARK = colors.HexColor("#0f3d7a")
_ALT_ROW = colors.HexColor("#eef3fb")
_NUM_RE = re.compile(r"^-?[\d,]+(\.\d+)?%?$")


def _font_for(text: str, base: str) -> tuple[str, int]:
    """Return (font, alignment) for a cell, switching to the Urdu font and
    right alignment for Arabic-script text."""
    urdu = register_fonts()
    if urdu and has_rtl(text):
        return urdu, TA_RIGHT
    return base, TA_LEFT


def _para(text, *, size=9, bold=False, white=False, base="Helvetica",
          align=None) -> Paragraph:
    text = "" if text is None else str(text)
    font = ("Helvetica-Bold" if bold else "Helvetica") if base == "Helvetica" else base
    use_font, auto_align = _font_for(text, font)
    if use_font != font and has_rtl(text):
        text = shape(text)
        font = use_font
    if align is None:
        align = TA_RIGHT if (_NUM_RE.match(text.strip()) and not has_rtl(text)) else auto_align
    style = ParagraphStyle(
        "c", fontName=font, fontSize=size, leading=size + 4,
        alignment=align, textColor=colors.white if white else colors.black,
    )
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe, style)


def _business_name() -> str:
    return config.APP_NAME_UR if i18n.get_language() == "ur" else config.APP_NAME


def _footer(canvas, doc) -> None:
    canvas.saveState()
    w, _h = doc.pagesize
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawString(15 * mm, 10 * mm, config.APP_NAME)
    canvas.drawRightString(
        w - 15 * mm, 10 * mm, f"{i18n.tr('page')} {doc.page}"
    )
    canvas.setStrokeColor(colors.HexColor("#d0d7e2"))
    canvas.line(15 * mm, 13 * mm, w - 15 * mm, 13 * mm)
    canvas.restoreState()


def write(report: ReportData, path: str | Path) -> Path:
    register_fonts()
    path = Path(path)

    ncols = len(report.headers) or 1
    wide = ncols > 8
    pagesize = landscape(A4) if wide else A4
    size = 9 if ncols <= 9 else (7 if ncols <= 12 else 6)

    doc = SimpleDocTemplate(
        str(path), pagesize=pagesize, title=report.title,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=18 * mm,
    )
    avail = pagesize[0] - 30 * mm

    # --- branded header band ---
    brand = _para(_business_name(), size=16, bold=True, white=True, align=TA_LEFT)
    title = _para(report.title, size=11, white=True, align=TA_LEFT)
    gen = _para(
        f"{i18n.tr('generated_on')}: {datetime.now():%Y-%m-%d %H:%M}",
        size=8, white=True, align=TA_LEFT,
    )
    head_tbl = Table([[brand], [title], [gen]], colWidths=[avail])
    head_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _BRAND),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (-1, -1), (-1, -1), 8),
    ]))

    story: list = [head_tbl, Spacer(1, 10)]

    # --- hero headline (e.g. Total business worth) ---
    if report.hero:
        label, value = report.hero
        htbl = Table(
            [[_para(label, size=10, bold=True, white=True, align=TA_LEFT)],
             [_para(value, size=20, bold=True, white=True, align=TA_LEFT)]],
            colWidths=[avail],
        )
        htbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#4f46e5")),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (0, 0), 8),
            ("BOTTOMPADDING", (-1, -1), (-1, -1), 10),
        ]))
        story.extend([htbl, Spacer(1, 10)])

    # --- stat tiles (overall numbers), 4 per row ---
    if report.tiles:
        per_row = 4
        tile_rows = [report.tiles[i:i + per_row]
                     for i in range(0, len(report.tiles), per_row)]
        for chunk in tile_rows:
            cells = []
            for label, value in chunk:
                inner = Table(
                    [[_para(label, size=7, bold=True, align=TA_LEFT)],
                     [_para(value, size=11, bold=True, align=TA_LEFT)]],
                    colWidths=[avail / per_row - 6],
                )
                inner.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), _ALT_ROW),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#c7d0de")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (0, 0), 5),
                    ("BOTTOMPADDING", (-1, -1), (-1, -1), 6),
                ]))
                cells.append(inner)
            while len(cells) < per_row:
                cells.append("")
            wrap = Table([cells], colWidths=[avail / per_row] * per_row)
            wrap.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(wrap)
        story.append(Spacer(1, 4))

    def _data_table(headers: list[str], rows: list[list[str]],
                    bold_rows: list[int], fsize: int) -> Table:
        nc = max(len(headers), 1)
        data = [[_para(h, size=fsize, bold=True, white=True) for h in headers]]
        for i, row in enumerate(rows):
            data.append([
                _para(c, size=fsize, bold=(i in bold_rows)) for c in row
            ])
        t = Table(data, repeatRows=1, colWidths=[avail / nc] * nc)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), _BRAND_DARK),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c7d0de")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT_ROW]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        for i in bold_rows:  # tinted result rows
            style.append(
                ("BACKGROUND", (0, i + 1), (-1, i + 1), colors.HexColor("#e2e8f0"))
            )
        # Bold vertical divider line (e.g. split ledger's left|right split).
        if report.divider_after is not None and 0 <= report.divider_after < nc:
            d = report.divider_after
            style.append(
                ("LINEAFTER", (d, 0), (d, -1), 1.8, colors.HexColor("#0f172a"))
            )
        t.setStyle(TableStyle(style))
        return t

    if report.sections:
        # --- titled sections, each its own table ---
        for sec in report.sections:
            story.append(Spacer(1, 6))
            story.append(_para(sec.title, size=11, bold=True, align=TA_LEFT))
            story.append(Spacer(1, 4))
            fsize = 9 if len(sec.headers) <= 9 else 7
            story.append(_data_table(sec.headers, sec.rows, sec.bold_rows, fsize))
    elif report.headers or report.rows:
        # --- classic single data table ---
        story.append(_data_table(report.headers, report.rows, [], size))

    # --- summary box ---
    if report.summary:
        story.append(Spacer(1, 12))
        srows = [[_para(label, size=size + 1, bold=True),
                  _para(value, size=size + 1, bold=True, align=TA_RIGHT)]
                 for label, value in report.summary]
        stbl = Table(srows, colWidths=[avail * 0.6, avail * 0.4])
        stbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
            ("LINEABOVE", (0, 0), (-1, 0), 1, _BRAND),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(stbl)

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path
