"""expense kind (business / house)

Revision ID: a71c4e92d5b8
Revises: 1b5e984e3641
Create Date: 2026-07-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a71c4e92d5b8'
down_revision: Union[str, None] = '1b5e984e3641'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('kind', sa.String(), nullable=False,
                      server_default='business')
        )


def downgrade() -> None:
    with op.batch_alter_table('expenses', schema=None) as batch_op:
        batch_op.drop_column('kind')
