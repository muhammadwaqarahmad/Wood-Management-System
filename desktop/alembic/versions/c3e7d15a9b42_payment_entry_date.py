"""payment entry_date (when typed) vs txn_date (when received)

Revision ID: c3e7d15a9b42
Revises: b9f2a4c7e1d3
Create Date: 2026-08-09

Adds ``payments.entry_date`` — the day a payment was actually booked, kept
separate from ``txn_date`` (the effective/received date that drives the
ledger and weekly settlement). Existing rows are backfilled from the day
part of ``created_at`` so nothing is left blank.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e7d15a9b42'
down_revision: Union[str, None] = 'b9f2a4c7e1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('entry_date', sa.Date(), nullable=True))
    # Backfill: the record's booking day = the date part of created_at, falling
    # back to txn_date. The "date part of a timestamp" spelling differs by
    # dialect: SQLite's date() vs Postgres' ::date cast (a bare CAST AS DATE is
    # unreliable on SQLite due to type affinity), so branch on the backend.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        date_expr = "date(created_at)"
    else:
        date_expr = "created_at::date"
    op.execute(
        f"UPDATE payments "
        f"SET entry_date = COALESCE({date_expr}, txn_date) "
        f"WHERE entry_date IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_column('entry_date')
