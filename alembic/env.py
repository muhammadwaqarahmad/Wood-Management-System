"""Alembic migration environment, wired to the Timber app.

- Connection URL comes from ``timber.config.database_url()`` so it
  honours the SQLite <-> PostgreSQL switch automatically.
- ``target_metadata`` is the app's ``Base.metadata`` (all 9 models),
  so ``--autogenerate`` can diff models against the live database.
- ``render_as_batch=True`` lets SQLite perform ALTERs (it can't do
  them natively; Alembic rebuilds the table behind the scenes).
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from timber.config import database_url
from timber.db.engine import Base
import timber.db.models  # noqa: F401 - registers all models on Base.metadata

config = context.config

# Feed our URL to Alembic (overrides the placeholder in alembic.ini).
# Escape % as %% so ConfigParser's interpolation doesn't choke on a URL-encoded
# password: special chars like @ / : become %40 %2F %3A via quote_plus, and a
# lone % is invalid interpolation syntax. ConfigParser resolves %% back to %
# when the URL is read, so SQLAlchemy still receives the correct connection URL.
config.set_main_option("sqlalchemy.url", database_url().replace("%", "%%"))

import logging as _logging

# Apply alembic.ini's logging ONLY when Alembic is driven from the command line
# (a bare process with no logging set up yet). The desktop app calls
# upgrade_to_head() during startup, which loads this env.py — and alembic.ini
# defines [logger_root] (level=WARNING, handlers=console). fileConfig would
# therefore RESET the root logger the app just configured: dropping it to
# WARNING and replacing the app's file handler. The app then wrote NO log file
# for the rest of the session (every log stopped right after "Starting ..."),
# which hid real errors on client PCs. If the root logger already has handlers,
# someone (the app) configured logging — leave it alone.
if config.config_file_name is not None and not _logging.getLogger().handlers:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection ('--sql' mode)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
