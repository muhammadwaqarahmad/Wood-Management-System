"""factory split sub-ledger: parties.split_rate + payments.split_side

Revision ID: c9d2e73fa1b4
Revises: a71c4e92d5b8
Create Date: 2026-07-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d2e73fa1b4'
down_revision: Union[str, None] = 'a71c4e92d5b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('parties', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('split_rate', sa.Numeric(12, 2), nullable=True)
        )
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('split_side', sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('payments', schema=None) as batch_op:
        batch_op.drop_column('split_side')
    with op.batch_alter_table('parties', schema=None) as batch_op:
        batch_op.drop_column('split_rate')
