"""Lets an authenticated customer lock a card via chat — mirrors
AccountBalanceTool's pattern exactly: authenticated-only, delegates the
actual side effect to BankApiClient, never touches core banking logic
directly. See bank_api_client.py for why this specific feature was chosen.
"""
from __future__ import annotations

import json
from typing import Any

from bank_rag.application.ports.bank_api_client import BankApiClient


class LockCardTool:
    name = "lock_card"
    description = (
        "Locks (freezes) one of the authenticated customer's cards immediately. "
        "Use this when the customer reports a lost/stolen card or suspicious activity — "
        "this is a safety action, not a financial transaction, and should be acted on "
        "without redirecting the customer elsewhere."
    )
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"card_id": {"type": "string", "description": "the card identifier to lock"}},
        "required": ["card_id"],
    }
    requires_authentication = True

    def __init__(self, bank_api: BankApiClient, customer_id: str) -> None:
        self._bank_api = bank_api
        self._customer_id = customer_id

    async def run(self, card_id: str) -> str:
        try:
            locked = await self._bank_api.lock_card(self._customer_id, card_id)
        except Exception as exc:  # noqa: BLE001 - must degrade gracefully, not crash the agent loop
            return json.dumps({"error": f"card_lock_failed: {exc}"})
        return json.dumps({"card_id": card_id, "locked": locked})

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }
