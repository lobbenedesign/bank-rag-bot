from __future__ import annotations

from typing import Protocol


class BankApiClient(Protocol):
    """Port towards the core-banking system, for tools with real side effects
    or that read account-scoped data. Never called by the RAG path directly —
    only through an explicit, whitelisted Tool (see agents/tools).
    """

    async def get_account_balance(self, customer_id: str, account_id: str) -> float: ...

    async def list_accounts(self, customer_id: str) -> list[dict]: ...

    async def lock_card(self, customer_id: str, card_id: str) -> bool:
        """Freezes a card immediately. The single most-cited high-value
        feature across production banking chatbots (Capital One's Eno,
        Commonwealth Bank's Ceba, Bank of America's Erica) — a customer can
        act on a lost/stolen card in seconds instead of waiting on hold.
        Returns True if the card is now locked.
        """
        ...
