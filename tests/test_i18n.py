"""Tests for the translation layer."""

import pytest
from PySide6.QtCore import Qt

import timber.core.app_settings as app_settings
import timber.i18n as i18n


@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    """Isolate language persistence to a temp file per test."""
    monkeypatch.setattr(app_settings, "_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(i18n, "_current", None)
    yield


def test_tr_english(temp_settings):
    i18n.set_language("en")
    assert i18n.tr("save") == "Save"


def test_tr_urdu(temp_settings):
    i18n.set_language("ur")
    assert i18n.tr("save") == "محفوظ کریں"


def test_set_language_persists(temp_settings):
    i18n.set_language("ur")
    assert app_settings.get("language") == "ur"


def test_unknown_key_returns_key(temp_settings):
    i18n.set_language("en")
    assert i18n.tr("no_such_key") == "no_such_key"


def test_invalid_language_rejected(temp_settings):
    with pytest.raises(ValueError):
        i18n.set_language("fr")


def test_layout_direction(temp_settings):
    i18n.set_language("ur")
    assert i18n.layout_direction() == Qt.LayoutDirection.RightToLeft
    i18n.set_language("en")
    assert i18n.layout_direction() == Qt.LayoutDirection.LeftToRight


def test_every_string_has_both_languages():
    missing = [
        key
        for key, entry in i18n.STRINGS.items()
        if "en" not in entry or "ur" not in entry
    ]
    assert not missing, f"strings missing a language: {missing}"
