"""HTTP adapter towards the bank's internal core-banking API.

Isolated in `infrastructure/` so authentication headers, retries, timeouts
and the internal API's actual URL scheme stay out of the agent/tool layer.
"""
from __future__ import annotations

import httpx


class CoreBankingHttpClient:
    def __init__(self, base_url: str, service_token: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url
        self._headers = {"Authorization": f"Bearer {service_token}"}
        self._timeout = timeout_seconds

    async def get_account_balance(self, customer_id: str, account_id: str) -> float:
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=self._timeout) as client:
            response = await client.get(f"/customers/{customer_id}/accounts/{account_id}/balance")
            response.raise_for_status()
            return float(response.json()["balance"])

    async def list_accounts(self, customer_id: str) -> list[dict]:
        async with httpx.AsyncClient(base_url=self._base_url, headers=self._headers, timeout=self._timeout) as client:
            response = await client.get(f"/customers/{customer_id}/accounts")
            response.raise_for_status()
            return response.json()["accounts"]
