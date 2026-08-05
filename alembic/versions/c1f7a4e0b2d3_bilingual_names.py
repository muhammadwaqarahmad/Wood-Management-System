"""bilingual names for parties and bank accounts

Adds name_en / name_ur to parties and bank_accounts and backfills them from
the client's known (english, urdu) master-data pairs. Rows that don't match a
known pair (custom entries) get the same text in both languages so nothing
ever displays blank.

Revision ID: c1f7a4e0b2d3
Revises: b8e6d4c1a209
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1f7a4e0b2d3'
down_revision: Union[str, None] = 'b8e6d4c1a209'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _pairs():
    """(english, urdu) pairs from the seed data, plus the special accounts."""
    from timber.db.seed_master import (
        BANK_ACCOUNTS, FACTORIES, SUPPLIERS, UNKNOWN_FACTORY, UNKNOWN_SUPPLIER,
    )

    party_pairs = list(SUPPLIERS) + list(FACTORIES) + [UNKNOWN_SUPPLIER, UNKNOWN_FACTORY]
    account_pairs = list(BANK_ACCOUNTS) + [("Cash", "نقد")]
    return party_pairs, account_pairs


def _backfill(table: str, pairs) -> None:
    conn = op.get_bind()
    ur_to_en = {ur: en for en, ur in pairs}
    en_to_ur = {en: ur for en, ur in pairs}
    rows = conn.execute(sa.text(f"SELECT id, name FROM {table}")).fetchall()
    for row_id, name in rows:
        if name in ur_to_en:              # existing name is the Urdu one
            en, ur = ur_to_en[name], name
        elif name in en_to_ur:            # existing name is the English one
            en, ur = name, en_to_ur[name]
        else:                             # custom row: show the same in both
            en = ur = name
        conn.execute(
            sa.text(
                f"UPDATE {table} SET name_en = :en, name_ur = :ur WHERE id = :id"
            ),
            {"en": en, "ur": ur, "id": row_id},
        )


def upgrade() -> None:
    for table in ("parties", "bank_accounts"):
        op.add_column(table, sa.Column("name_en", sa.String(), nullable=True))
        op.add_column(table, sa.Column("name_ur", sa.String(), nullable=True))

    party_pairs, account_pairs = _pairs()
    _backfill("parties", party_pairs)
    _backfill("bank_accounts", account_pairs)


def downgrade() -> None:
    for table in ("parties", "bank_accounts"):
        op.drop_column(table, "name_ur")
        op.drop_column(table, "name_en")
