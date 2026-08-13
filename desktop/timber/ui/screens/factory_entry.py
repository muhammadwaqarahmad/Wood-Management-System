"""Factory (sale) entry screen."""

from __future__ import annotations

from timber.core.current_user import CurrentUser
from timber.core.transaction_service import create_factory_txn
from timber.db.models.party import PARTY_FACTORY
from timber.ui.screens.txn_form import TxnEntryForm


class FactoryEntryScreen(TxnEntryForm):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(
            current_user,
            party_type=PARTY_FACTORY,
            party_label_key="factory",
            save_callable=create_factory_txn,
            title_key="factory_sale",
            parent=parent,
        )
