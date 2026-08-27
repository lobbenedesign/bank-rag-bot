from __future__ import annotations

from typing import Protocol


class BankApiClient(Protocol):
    """Port towards the core-banking system, for tools with real side effects
    or that read account-scoped data. Never called by the RAG path directly —
    only through an explicit, whitelisted Tool (see agents/tools).
    """

    async def get_account_balance(self, customer_id: str, account_id: str) -> float: ...

    async def list_accounts(self, customer_id: str) -> list[dict]: ...
