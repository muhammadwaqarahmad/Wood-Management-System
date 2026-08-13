"""Local, per-PC application preferences (e.g. language).

Stored as JSON in ``storage/settings.json`` so it is available before
login and is independent of the shared database. Use the DB for shared
business data; use this for this machine's UI preferences.
"""

from __future__ import annotations

import json
from typing import Any

from timber import config

_PATH = config.STORAGE_DIR / "settings.json"


def _load() -> dict:
    try:
        return json.loads(_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get(key: str, default: Any = None) -> Any:
    return _load().get(key, default)


def set(key: str, value: Any) -> None:  # noqa: A001 - intentional simple API
    data = _load()
    data[key] = value
    config.ensure_dirs()
    _PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
