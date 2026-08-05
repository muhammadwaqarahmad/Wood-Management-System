"""Tests for the theme engine."""

from timber.core import app_settings
from timber.ui import theme


def test_theme_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "_PATH", tmp_path / "s.json")
    monkeypatch.setattr(theme, "_current", None)
    theme.set_theme("dark")
    assert theme.get_theme() == "dark"
    monkeypatch.setattr(theme, "_current", None)  # force reload from disk
    assert theme.get_theme() == "dark"


def test_build_stylesheet_both_themes():
    for name in theme.THEMES:
        css = theme.build_stylesheet(name)
        assert "QMainWindow" in css
        assert "$" not in css  # all tokens substituted


def test_unknown_theme_rejected():
    import pytest

    with pytest.raises(ValueError):
        theme.set_theme("neon")
