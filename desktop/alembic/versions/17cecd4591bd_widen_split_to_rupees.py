"""widen split to rupees

Revision ID: 17cecd4591bd
Revises: f53b1510ebf5
Create Date: 2026-06-27 18:03:30.928746

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17cecd4591bd'
down_revision: Union[str, None] = 'f53b1510ebf5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Split columns now store a rupee amount (primary payer's share), not a
    # percentage -> widen Numeric(5,2) to Numeric(12,2).
    with op.batch_alter_table('combined_txns', schema=None) as batch_op:
        for col in ('loading_split', 'freight_split', 'unloading_split'):
            batch_op.alter_column(
                col,
                existing_type=sa.Numeric(precision=5, scale=2),
                type_=sa.Numeric(precision=12, scale=2),
                existing_nullable=False,
            )


def downgrade() -> None:
    with op.batch_alter_table('combined_txns', schema=None) as batch_op:
        for col in ('loading_split', 'freight_split', 'unloading_split'):
            batch_op.alter_column(
                col,
                existing_type=sa.Numeric(precision=12, scale=2),
                type_=sa.Numeric(precision=5, scale=2),
                existing_nullable=False,
            )
