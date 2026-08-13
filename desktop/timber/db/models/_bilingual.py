"""Bilingual name support for master-data rows (parties, bank accounts).

The client's staff work in either Urdu or English. The *same* supplier or
account must read in whichever language the user has the app set to. So we
store the name twice — ``name_en`` and ``name_ur`` — and expose a single
``name`` that resolves to the current language automatically.

``name`` is a hybrid, so:
  * ``obj.name``           → the localized string (fallback to the other
    language, then to the physical ``name`` column) — every existing read
    site localizes for free.
  * ``Model.name`` in SQL  → ``coalesce(<current-lang column>, name)`` so
    ``order_by`` / ``where`` also follow the current language.

The physical ``name`` column is kept (mapped as ``_name``) as a non-null
fallback and a stable key for language-independent lookups.
"""

from __future__ import annotations

from sqlalchemy import String, func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column


def _lang() -> str:
    # Imported lazily so the model layer doesn't pull in PyQt at import time.
    from timber import i18n

    return i18n.get_language()


class BilingualName:
    """Mixin: a language-aware ``name`` backed by ``name_en`` / ``name_ur``."""

    # Physical column stays "name" (non-null); accessed as ``_name``.
    _name: Mapped[str] = mapped_column("name")
    name_en: Mapped[str | None] = mapped_column(String, default=None)
    name_ur: Mapped[str | None] = mapped_column(String, default=None)

    @hybrid_property
    def name(self) -> str:
        lang = _lang()
        primary = self.name_ur if lang == "ur" else self.name_en
        other = self.name_en if lang == "ur" else self.name_ur
        return primary or other or self._name

    @name.inplace.setter
    def _name_setter(self, value: str) -> None:
        # Assigning ``.name`` (or constructing with ``name=``) fills the
        # current language's field and keeps the physical column populated.
        if _lang() == "ur":
            self.name_ur = value
        else:
            self.name_en = value
        self._name = value

    @name.inplace.expression
    @classmethod
    def _name_expression(cls):
        col = cls.name_ur if _lang() == "ur" else cls.name_en
        return func.coalesce(col, cls._name)

    def set_names(self, *, en: str | None, ur: str | None) -> None:
        """Set both language names at once. At least one must be non-empty;
        the physical fallback prefers the current language."""
        en = (en or "").strip() or None
        ur = (ur or "").strip() or None
        self.name_en = en
        self.name_ur = ur
        primary = ur if _lang() == "ur" else en
        self._name = primary or en or ur or ""
