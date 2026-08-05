"""Bring the database schema up to date.

Alembic is the single source of truth for the schema. This helper just
runs ``alembic upgrade head`` from Python so the app (or a first-run
installer) can ensure all migrations are applied:

    python -m timber.db.init_db

Equivalent CLI:  python -m alembic upgrade head

To create a NEW migration after changing a model, use the CLI:
    python -m alembic revision --autogenerate -m "describe change"
    python -m alembic upgrade head
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config

from timber import config


def upgrade_to_head() -> None:
    # Use the bundled alembic.ini when present, else a bare Config; either
    # way force an ABSOLUTE script_location so it resolves correctly whether
    # running from source or from a packaged .exe (CWD-independent).
    cfg = Config(str(config.ALEMBIC_INI)) if config.ALEMBIC_INI.exists() else Config()
    cfg.set_main_option("script_location", str(config.ALEMBIC_DIR))
    command.upgrade(cfg, "head")
    print("Database is at the latest migration (head).")


if __name__ == "__main__":
    upgrade_to_head()
