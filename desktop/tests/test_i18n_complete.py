"""Translation completeness + language persistence."""

from timber import i18n
from timber.core import app_settings


def test_every_string_has_all_languages():
    for key, entry in i18n.STRINGS.items():
        for lang in i18n.LANGUAGES:
            assert entry.get(lang), f"String {key!r} missing/empty for {lang!r}"


def test_tr_falls_back_to_key():
    assert i18n.tr("no_such_key_at_all") == "no_such_key_at_all"


def test_language_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(i18n, "_current", None)

    i18n.set_language("en")
    assert i18n.get_language() == "en"

    # Force a reload from disk -> the choice was persisted.
    monkeypatch.setattr(i18n, "_current", None)
    assert i18n.get_language() == "en"


def test_layout_direction_follows_language(monkeypatch):
    from PySide6.QtCore import Qt

    monkeypatch.setattr(i18n, "_current", "ur")
    assert i18n.layout_direction() == Qt.LayoutDirection.RightToLeft
    monkeypatch.setattr(i18n, "_current", "en")
    assert i18n.layout_direction() == Qt.LayoutDirection.LeftToRight
