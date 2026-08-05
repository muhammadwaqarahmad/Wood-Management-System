"""Supplier (bapari) ledger — a rich, filtered per-supplier statement."""

from __future__ import annotations

from timber.core.current_user import CurrentUser
from timber.db.models.party import PARTY_BAPARI
from timber.ui.screens.party_statement_screen import PartyStatementScreen


class PartyLedgerScreen(PartyStatementScreen):
    def __init__(self, current_user: CurrentUser, parent=None) -> None:
        super().__init__(current_user, PARTY_BAPARI, "party_ledger", parent)
