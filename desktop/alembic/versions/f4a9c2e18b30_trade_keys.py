"""trade dedup keys — unique (date, vehicle, weight) guard against double entry

Revision ID: f4a9c2e18b30
Revises: e7b3c1d9a2f4
Create Date: 2026-07-07

Back-fills one key per existing non-void trade so the guard also covers
data that was already entered. Existing exact duplicates (if any) are left
un-keyed rather than failing the migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a9c2e18b30'
down_revision: Union[str, None] = 'e7b3c1d9a2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'trade_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('txn_date', sa.Date(), nullable=False),
        sa.Column('vehicle_key', sa.String(), nullable=False),
        sa.Column('total_weight', sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(
            ['group_id'], ['combined_txns.id'],
            name=op.f('fk_trade_keys_group_id_combined_txns'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_trade_keys')),
        sa.UniqueConstraint(
            'txn_date', 'vehicle_key', 'total_weight', name='uq_trade_keys_dedup'
        ),
    )

    # Back-fill a key for every existing truck (group) with a vehicle number.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        """
        SELECT c.group_id AS gid,
               b.txn_date AS d,
               LOWER(TRIM(b.vehicle_no)) AS vk,
               SUM(b.weight) AS w
        FROM combined_txns c
        JOIN bapari_txns b ON b.id = c.bapari_txn_id
        WHERE b.vehicle_no IS NOT NULL
          AND TRIM(b.vehicle_no) <> ''
          AND NOT b.is_void
        GROUP BY c.group_id, b.txn_date, LOWER(TRIM(b.vehicle_no))
        """
    )).fetchall()
    seen: set = set()
    for gid, d, vk, w in rows:
        weight = round(float(w or 0), 2)
        key = (str(d), vk, weight)
        if key in seen:
            continue  # already-existing duplicate — skip, don't fail the migration
        seen.add(key)
        conn.execute(
            sa.text(
                "INSERT INTO trade_keys (group_id, txn_date, vehicle_key, total_weight)"
                " VALUES (:g, :d, :v, :w)"
            ),
            {"g": gid, "d": d, "v": vk, "w": weight},
        )


def downgrade() -> None:
    op.drop_table('trade_keys')
