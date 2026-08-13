"""unknown payments carry a direction

Revision ID: e4b9d70c15af
Revises: d8c3f21a6b47
Create Date: 2026-07-22

Adds ``unknown_payments.direction``. An unknown record used to be receive-only
by definition — money that landed in an account before we knew who sent it — so
its amount was always ADDED to that account's balance. The mirror case is just
as real: an unexplained debit that left an account before we know who it went
to. That needs to subtract instead, which it cannot do without this column.

Every existing row is a receipt, so "in" is both the backfill and the default;
account balances are unchanged by this migration.

Defensive like the rest of the chain: inspects the table first so a database
that already has the column (or is being re-stamped) upgrades cleanly.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b9d70c15af"
down_revision: Union[str, None] = "d8c3f21a6b47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "unknown_payments"
_COLUMN = "direction"


def _columns() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return set()
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    cols = _columns()
    if not cols or _COLUMN in cols:
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(
            sa.Column(_COLUMN, sa.String(), nullable=False, server_default="in")
        )
    # Existing rows are all receipts; make that explicit rather than relying on
    # the server default alone.
    op.execute(f"UPDATE {_TABLE} SET {_COLUMN} = 'in' WHERE {_COLUMN} IS NULL")


def downgrade() -> None:
    if _COLUMN in _columns():
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
