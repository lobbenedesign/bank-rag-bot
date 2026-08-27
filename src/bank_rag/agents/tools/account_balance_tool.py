"""Example of a tool with a real side effect / access to account-scoped data.

Registered only for authenticated conversations (see ToolRegistry.for_conversation).
This is the boundary a naive "RAG chatbot" answer usually forgets to draw: the
knowledge base must never contain a customer's real balance, it must be fetched
live, per-request, through an authorized API call.
"""
from __future__ import annotations

import json
from typing import Any

from bank_rag.application.ports.bank_api_client import BankApiClient


class AccountBalanceTool:
    name = "get_account_balance"
    description = "Returns the authenticated customer's balance for a given account id."
    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"account_id": {"type": "string"}},
        "required": ["account_id"],
    }
    requires_authentication = True

    def __init__(self, bank_api: BankApiClient, customer_id: str) -> None:
        self._bank_api = bank_api
        self._customer_id = customer_id

    async def run(self, account_id: str) -> str:
        try:
            balance = await self._bank_api.get_account_balance(self._customer_id, account_id)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"balance_lookup_failed: {exc}"})
        return json.dumps({"account_id": account_id, "balance": balance})

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }
