"""DB-backed app settings + business-name application.

The business name lives in the ``app_settings`` table (keys ``business_name_en``
/ ``business_name_ur``). The env vars TIMBER_BUSINESS_NAME[_UR] remain the
default when unset. ``apply_business_name`` pushes the active name into
``config`` and ``i18n`` so every window title, PDF/Excel export and the
"we paid" (payer_us) label reflect it — live in the running process.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from timber import config, i18n
from timber.db.models.app_setting import AppSetting

BUSINESS_NAME_EN = "business_name_en"
BUSINESS_NAME_UR = "business_name_ur"


def get_setting(session: Session, key: str, default: str | None = None) -> str | None:
    row = session.get(AppSetting, key)
    return row.value if row is not None else default


def set_setting(session: Session, key: str, value: str) -> None:
    """Upsert a setting. Caller commits."""
    row = session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def business_name(session: Session) -> tuple[str, str]:
    """The active (English, Urdu) business name — the stored value, or the env
    default when a key is unset/blank."""
    en = get_setting(session, BUSINESS_NAME_EN) or config.APP_NAME
    ur = get_setting(session, BUSINESS_NAME_UR) or config.APP_NAME_UR
    return en, ur


def apply_business_name(en: str, ur: str) -> None:
    """Push the active name into config + i18n so the whole app uses it now."""
    config.APP_NAME = en
    config.APP_NAME_UR = ur
    for key in ("app_name", "payer_us"):
        if key in i18n.STRINGS:
            i18n.STRINGS[key] = {"en": en, "ur": ur}


def load_and_apply_business_name(session: Session) -> None:
    """Read the stored business name and apply it. Called once at startup by the
    desktop app and the API so both honour the DB-configured name."""
    en, ur = business_name(session)
    apply_business_name(en, ur)


def save_business_name(session: Session, en: str, ur: str) -> None:
    """Persist a new business name AND apply it live. Caller commits."""
    en = (en or "").strip()
    ur = (ur or "").strip()
    if not en and not ur:
        raise ValueError("Business name cannot be empty.")
    # Keep both sides populated so titles never go blank in either language.
    en = en or ur
    ur = ur or en
    set_setting(session, BUSINESS_NAME_EN, en)
    set_setting(session, BUSINESS_NAME_UR, ur)
    apply_business_name(en, ur)
