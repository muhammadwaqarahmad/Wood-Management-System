"""per-wood-type split rates for factories

Revision ID: b9f2a4c7e1d3
Revises: e4b9d70c15af
Create Date: 2026-08-09

Adds ``factory_split_rates`` (factory + wood type -> split rate). Seeds it
from each enrolled factory's existing flat ``parties.split_rate`` for every
wood type it has already traded, so every historical sub-ledger balance is
preserved exactly. Wood types traded later start with no split (whole rate
on the weekly side) until configured.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9f2a4c7e1d3'
down_revision: Union[str, None] = 'e4b9d70c15af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'factory_split_rates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('factory_id', sa.Integer(), nullable=False),
        sa.Column('wood_type_id', sa.Integer(), nullable=False),
        sa.Column('split_rate', sa.Numeric(12, 2),
                  nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['factory_id'], ['parties.id']),
        sa.ForeignKeyConstraint(['wood_type_id'], ['wood_types.id']),
        sa.UniqueConstraint('factory_id', 'wood_type_id',
                            name='uq_factory_split_wood'),
    )
    # Seed: copy the current flat split_rate onto every wood type each enrolled
    # factory has actually traded. DISTINCT keeps one row per (factory, wood).
    # ``NOT is_void`` is portable across SQLite (0/1) and Postgres (boolean).
    op.execute(
        """
        INSERT INTO factory_split_rates (factory_id, wood_type_id, split_rate)
        SELECT DISTINCT ft.party_id, ft.wood_type_id, p.split_rate
        FROM factory_txns ft
        JOIN parties p ON p.id = ft.party_id
        WHERE p.split_rate IS NOT NULL
          AND p.split_rate > 0
          AND ft.wood_type_id IS NOT NULL
          AND NOT ft.is_void
        """
    )


def downgrade() -> None:
    op.drop_table('factory_split_rates')
