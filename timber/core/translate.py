"""Live, two-way translation of free-text business data.

- Urdu UI: English data (names, notes) is shown in Urdu.
- English UI: Urdu data (typed by Urdu staff) is shown in English.

Fixed vocabulary (payment method, party type, ...) maps instantly from
the offline i18n dictionary. Everything else is translated online and
cached per direction in the shared ``translations`` table, so each unique
string is translated once and reused by every machine. Misses show the
original until the translation arrives (then the screen refreshes).
Degrades gracefully to the original when off or offline.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

from timber import config, i18n

# Fixed data values that already have offline Urdu in the i18n dictionary.
_ENUM_KEYS = {
    "cash", "online", "bank", "cheque",
    "bapari", "factory",
    "active", "inactive",
}

# In-memory cache: {(source_text, target_lang): translated}. From the DB.
_CACHE: dict[tuple[str, str], str] = {}
_LOADED = False
_ENQUEUE = None  # set by the UI worker: callable(text, target) -> None

_ARABIC = re.compile(r"[؀-ۿ]")          # any Urdu/Arabic letter
_HAS_ASCII_ALPHA = re.compile(r"[A-Za-z]")
_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

# Circuit breaker: on a PC with no internet (or a network that blocks the
# translate endpoint), every call would otherwise wait out the full timeout
# and fail — and the background worker would grind through the whole queue
# that way, taking minutes and making screens feel stuck. After a few
# consecutive failures we "open" the breaker and stop calling the network for
# a cooldown, so the queue drains instantly and the app stays responsive. One
# success closes it again.
_TIMEOUT = 5              # seconds per request (was 8 — long waits stack up)
_FAIL_THRESHOLD = 3      # consecutive failures before the breaker opens
_COOLDOWN = 600.0        # seconds to stay offline before trying again
_fail_count = 0
_breaker_until = 0.0     # monotonic time until which we skip the network


def set_enqueue(fn) -> None:
    """Register the background worker's enqueue function."""
    global _ENQUEUE
    _ENQUEUE = fn


def load_cache(session) -> None:
    """Load all cached translations into memory (call once at startup)."""
    global _LOADED
    from timber.db.models import Translation

    _CACHE.clear()
    for t in session.query(Translation):
        _CACHE[(t.source_text, t.target_lang)] = t.translated_text
    _LOADED = True


def remember(source_text: str, target: str, translated_text: str) -> None:
    """Add a freshly translated string to the in-memory cache."""
    _CACHE[(source_text, target)] = translated_text


def is_cached(text: str, target: str) -> bool:
    return (text, target) in _CACHE


def _should_translate(text: str, target: str) -> bool:
    """True if ``text`` is worth translating into ``target`` (skip numbers,
    dates, codes, very long text, and text already in the target script)."""
    s = text.strip()
    if not s or len(s) > 200:
        return False
    if target == "ur":
        # English -> Urdu: needs Latin letters and not already Urdu.
        return bool(_HAS_ASCII_ALPHA.search(s)) and not _ARABIC.search(s)
    # Urdu -> English: needs Arabic-script letters.
    return bool(_ARABIC.search(s))


def tr_data(text):
    """Return ``text`` in the active UI language. Translates the other
    language's free text (cached); enum values map offline."""
    if not config.TRANSLATE_ENABLED:
        return text
    if not isinstance(text, str) or not text.strip():
        return text

    lang = i18n.get_language()          # the language we want to SHOW in
    target = "ur" if lang == "ur" else "en"
    key = text.strip()

    # Fixed vocabulary -> offline dictionary (only when showing Urdu; the
    # English codes are already English).
    if target == "ur" and key.lower() in _ENUM_KEYS:
        return i18n.tr(key.lower())

    if not _should_translate(key, target):
        return text

    cached = _CACHE.get((key, target))
    if cached is not None:
        return cached

    if _ENQUEUE is not None:
        _ENQUEUE(key, target)
    return text  # show the original until the translation arrives


def remote_translate(text: str, target: str) -> str | None:
    """Translate one string online. Source language is inferred from the
    target (en<->ur). Returns None on any failure. Uses a circuit breaker so
    an unreachable endpoint can't make the worker block for minutes."""
    global _fail_count, _breaker_until
    if time.monotonic() < _breaker_until:
        return None  # breaker open: don't touch the network during cooldown
    source = "en" if target == "ur" else "ur"
    try:
        params = urllib.parse.urlencode(
            {"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text}
        )
        req = urllib.request.Request(
            f"{_TRANSLATE_URL}?{params}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _fail_count = 0  # the network answered — breaker stays closed
        parts = [seg[0] for seg in data[0] if seg and seg[0]]
        result = "".join(parts).strip()
        return result or None
    except Exception:  # noqa: BLE001 - network/parse errors -> graceful fallback
        _fail_count += 1
        if _fail_count >= _FAIL_THRESHOLD:
            _breaker_until = time.monotonic() + _COOLDOWN
            _fail_count = 0
        return None
