"""Application logging — rotating file log + console.

Call ``setup_logging()`` once at startup. Logs go to
``storage/logs/timber.log`` (rotated) so issues in the field leave a
trace we can inspect.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from timber import config

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    config.ensure_dirs()

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        config.LOG_DIR / "timber.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console)

    _configured = True
