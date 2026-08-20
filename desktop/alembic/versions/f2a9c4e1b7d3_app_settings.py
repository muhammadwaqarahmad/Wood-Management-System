"""app_settings key-value table (DB-backed business name, etc.)

Revision ID: f2a9c4e1b7d3
Revises: c3e7d15a9b42
Create Date: 2026-08-20

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f2a9c4e1b7d3"
down_revision: Union[str, None] = "c3e7d15a9b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
