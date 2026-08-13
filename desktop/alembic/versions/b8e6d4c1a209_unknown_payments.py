"""unknown (unattributed) receipts

Revision ID: b8e6d4c1a209
Revises: f4a9c2e18b30
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e6d4c1a209'
down_revision: Union[str, None] = 'f4a9c2e18b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'unknown_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('txn_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(12, 2), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('method', sa.String(), nullable=False),
        sa.Column('reference_no', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('is_void', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(
            ['bank_account_id'], ['bank_accounts.id'],
            name=op.f('fk_unknown_payments_bank_account_id_bank_accounts'),
        ),
        sa.ForeignKeyConstraint(
            ['created_by'], ['users.id'],
            name=op.f('fk_unknown_payments_created_by_users'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_unknown_payments')),
    )
    op.create_index(
        'ix_unknown_payments_bank_account', 'unknown_payments', ['bank_account_id']
    )


def downgrade() -> None:
    op.drop_index('ix_unknown_payments_bank_account', table_name='unknown_payments')
    op.drop_table('unknown_payments')
