"""wood types get default rates (one per side of the trade)

Revision ID: d8c3f21a6b47
Revises: c1f7a4e0b2d3
Create Date: 2026-07-19

Adds ``wood_types.default_supplier_rate`` and ``default_factory_rate`` — one
per side of the trade (what we pay the supplier, what we charge the factory).
Buy & Sell pre-fills both from the chosen wood so the common case needs no
typing; either can still be edited on the load itself, so these are only
starting values.

Existing rows default to 0.00, which the UI treats as "no default set" and
simply leaves that rate field alone.

Defensive on purpose: an earlier draft of this same revision added a single
``default_rate`` column. Any database that ran that draft is already stamped
with this revision, so the upgrade inspects the table and reconciles whatever
it finds rather than assuming a clean starting point.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8c3f21a6b47"
down_revision: Union[str, None] = "c1f7a4e0b2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WANTED = ("default_supplier_rate", "default_factory_rate")


def _columns() -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in sa.inspect(bind).get_columns("wood_types")}


def upgrade() -> None:
    cols = _columns()
    with op.batch_alter_table("wood_types") as batch:
        for name in _WANTED:
            if name not in cols:
                batch.add_column(
                    sa.Column(name, sa.Numeric(12, 2), nullable=False,
                              server_default="0")
                )

    # Carry a draft single-rate column over to the supplier side, then drop it.
    if "default_rate" in cols:
        op.execute(
            "UPDATE wood_types SET default_supplier_rate = default_rate "
            "WHERE default_supplier_rate = 0"
        )
        with op.batch_alter_table("wood_types") as batch:
            batch.drop_column("default_rate")


def downgrade() -> None:
    cols = _columns()
    with op.batch_alter_table("wood_types") as batch:
        for name in _WANTED:
            if name in cols:
                batch.drop_column(name)
