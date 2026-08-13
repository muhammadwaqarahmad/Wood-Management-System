"""performance indexes for years of daily entries

Every hot lookup gets an index: per-party ledgers, per-account bank
balances, FIFO allocations, trade grouping and date filters.

Revision ID: e7b3c1d9a2f4
Revises: d3f1a8b2c4e5
Create Date: 2026-07-06

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e7b3c1d9a2f4'
down_revision: Union[str, None] = 'd3f1a8b2c4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    # per-party ledgers (loads + payments filtered by party, ordered by date)
    ("ix_bapari_txns_party_date", "bapari_txns", ["party_id", "txn_date"]),
    ("ix_factory_txns_party_date", "factory_txns", ["party_id", "txn_date"]),
    ("ix_payments_party_date", "payments", ["party_id", "txn_date"]),
    # bank balances (per-account scans)
    ("ix_payments_bank_account", "payments", ["bank_account_id"]),
    ("ix_expenses_bank_account", "expenses", ["bank_account_id"]),
    ("ix_expenses_date", "expenses", ["txn_date"]),
    ("ix_transfers_from", "account_transfers", ["from_account_id"]),
    ("ix_transfers_to", "account_transfers", ["to_account_id"]),
    ("ix_loans_bank_account", "loans", ["bank_account_id"]),
    ("ix_loan_repayments_loan", "loan_repayments", ["loan_id"]),
    ("ix_loan_repayments_bank", "loan_repayments", ["bank_account_id"]),
    # trades (date filters, mixed-load grouping, joins to the two sides)
    ("ix_combined_txns_date", "combined_txns", ["txn_date"]),
    ("ix_combined_txns_group", "combined_txns", ["group_id"]),
    ("ix_combined_txns_bapari", "combined_txns", ["bapari_txn_id"]),
    ("ix_combined_txns_factory", "combined_txns", ["factory_txn_id"]),
    # FIFO allocations (paid-per-load lookups)
    ("ix_allocations_payment", "payment_allocations", ["payment_id"]),
    ("ix_allocations_txn", "payment_allocations", ["kind", "txn_id"]),
]


def upgrade() -> None:
    for name, table, cols in _INDEXES:
        op.create_index(name, table, cols)


def downgrade() -> None:
    for name, table, _cols in _INDEXES:
        op.drop_index(name, table_name=table)
