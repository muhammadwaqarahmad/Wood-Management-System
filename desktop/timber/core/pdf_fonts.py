"""Urdu font registration and text shaping for ReportLab.

ReportLab does no complex-script shaping, so Urdu/Arabic must be
reshaped (joined forms) and bidi-reordered before drawing. Drop a
Noto Nastaliq Urdu .ttf into ``timber/resources/fonts/`` to enable it.
"""

from __future__ import annotations

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from timber import config

URDU_FONT_NAME = "UrduFont"
_state: dict = {"checked": False, "name": None}


def register_fonts() -> str | None:
    """Register the Urdu TTF if present. Returns the font name or None."""
    if _state["checked"]:
        return _state["name"]
    _state["checked"] = True

    candidates = sorted(config.FONTS_DIR.glob("*.ttf"))
    # Prefer a Naskh font (Amiri / Noto Naskh): these carry the Arabic
    # presentation-form glyphs that arabic_reshaper produces, so Urdu text
    # renders correctly. Nastaliq fonts often miss those -> dotted boxes.
    def _rank(p):
        n = p.name.lower()
        for i, key in enumerate(("amiri", "naskh", "scheherazade", "arabic")):
            if key in n:
                return i
        return 99
    chosen = sorted(candidates, key=_rank)
    if chosen:
        try:
            pdfmetrics.registerFont(TTFont(URDU_FONT_NAME, str(chosen[0])))
            _state["name"] = URDU_FONT_NAME
        except Exception:  # noqa: BLE001 - bad font file, fall back silently
            _state["name"] = None
    return _state["name"]


def has_rtl(text: str) -> bool:
    """True if the text contains Arabic/Urdu characters."""
    return any(
        "؀" <= ch <= "ۿ"
        or "ݐ" <= ch <= "ݿ"
        or "ﭐ" <= ch <= "﷿"
        or "ﹰ" <= ch <= "﻿"
        for ch in str(text)
    )


def shape(text: str) -> str:
    """Reshape + bidi-reorder Urdu text for correct PDF rendering."""
    try:
        import arabic_reshaper

        try:
            from bidi import get_display
        except ImportError:  # older python-bidi
            from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:  # noqa: BLE001 - shaping is best-effort
        return str(text)
