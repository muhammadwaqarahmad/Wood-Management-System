"""Factory ledger — a rich, filtered per-factory statement (receivables)."""

from __future__ import annotations

from timber.core.current_user import CurrentUser
from timber.db.models.party import PARTY_FACTORY
from timber.ui.screens.party_statement_screen import PartyStatementScreen


class FactoryLedgerScreen(PartyStatementScreen):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(current_user, PARTY_FACTORY, "factory_ledger", parent)
