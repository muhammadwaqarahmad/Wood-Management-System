"""Bapari (purchase) entry screen."""

from __future__ import annotations

from timber.core.current_user import CurrentUser
from timber.core.transaction_service import create_bapari_txn
from timber.db.models.party import PARTY_BAPARI
from timber.ui.screens.txn_form import TxnEntryForm


class BapariEntryScreen(TxnEntryForm):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(
            current_user,
            party_type=PARTY_BAPARI,
            party_label_key="bapari",
            save_callable=create_bapari_txn,
            title_key="bapari_purchase",
            parent=parent,
        )
