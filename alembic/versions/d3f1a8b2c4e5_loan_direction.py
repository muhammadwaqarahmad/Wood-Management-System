"""loan direction (taken / given)

Revision ID: d3f1a8b2c4e5
Revises: c9d2e73fa1b4
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f1a8b2c4e5'
down_revision: Union[str, None] = 'c9d2e73fa1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('loans', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('direction', sa.String(), nullable=False,
                      server_default='taken')
        )


def downgrade() -> None:
    with op.batch_alter_table('loans', schema=None) as batch_op:
        batch_op.drop_column('direction')
