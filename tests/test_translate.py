"""Two-way live translation: enum mapping, caching, enqueue, fallbacks."""

import pytest

from timber import config, i18n
from timber.core import translate
from timber.db.models import Translation


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    translate._CACHE.clear()
    translate.set_enqueue(None)
    monkeypatch.setattr(config, "TRANSLATE_ENABLED", True)
    yield
    translate._CACHE.clear()
    translate.set_enqueue(None)


def _lang(monkeypatch, lang):
    monkeypatch.setattr(i18n, "get_language", lambda: lang)


def test_should_translate_direction_aware():
    # English -> Urdu
    assert translate._should_translate("Karim Timber", "ur") is True
    assert translate._should_translate("نقد", "ur") is False        # already Urdu
    assert translate._should_translate("12,500.00", "ur") is False  # number
    # Urdu -> English
    assert translate._should_translate("کریم", "en") is True
    assert translate._should_translate("Karim", "en") is False      # already English
    assert translate._should_translate("2026-01-01", "en") is False


def test_english_text_in_english_ui_unchanged(monkeypatch):
    _lang(monkeypatch, "en")
    assert translate.tr_data("Karim") == "Karim"


def test_urdu_data_translated_for_english_user(monkeypatch):
    _lang(monkeypatch, "en")
    translate.remember("کریم", "en", "Karim")
    assert translate.tr_data("کریم") == "Karim"


def test_english_data_translated_for_urdu_user(monkeypatch):
    _lang(monkeypatch, "ur")
    translate.remember("Karim", "ur", "کریم")
    assert translate.tr_data("Karim") == "کریم"


def test_enum_uses_offline_dictionary(monkeypatch):
    _lang(monkeypatch, "ur")
    assert translate.tr_data("cash") == i18n.tr("cash")     # نقد
    assert translate.tr_data("Factory") == i18n.tr("factory")


def test_miss_enqueues_with_target(monkeypatch):
    _lang(monkeypatch, "en")
    queued = []
    translate.set_enqueue(lambda text, target: queued.append((text, target)))
    assert translate.tr_data("لاہور") == "لاہور"            # original until cached
    assert queued == [("لاہور", "en")]


def test_disabled_returns_original(monkeypatch):
    _lang(monkeypatch, "ur")
    monkeypatch.setattr(config, "TRANSLATE_ENABLED", False)
    assert translate.tr_data("Karim") == "Karim"


def test_load_cache_both_directions(session, monkeypatch):
    session.add(Translation(source_text="Lahore", target_lang="ur", translated_text="لاہور"))
    session.add(Translation(source_text="کراچی", target_lang="en", translated_text="Karachi"))
    session.flush()
    translate.load_cache(session)
    _lang(monkeypatch, "ur")
    assert translate.tr_data("Lahore") == "لاہور"
    _lang(monkeypatch, "en")
    assert translate.tr_data("کراچی") == "Karachi"
