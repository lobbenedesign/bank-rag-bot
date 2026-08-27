from __future__ import annotations

import json

import pytest

from bank_rag.agents.tools.lock_card_tool import LockCardTool


class FakeBankApiClient:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[tuple[str, str]] = []

    async def lock_card(self, customer_id: str, card_id: str) -> bool:
        self.calls.append((customer_id, card_id))
        if self.should_fail:
            raise RuntimeError("core banking unavailable")
        return True


@pytest.mark.asyncio
async def test_locks_the_correct_customers_card():
    bank_api = FakeBankApiClient()
    tool = LockCardTool(bank_api, customer_id="cust-42")

    result = json.loads(await tool.run(card_id="card-7"))

    assert result == {"card_id": "card-7", "locked": True}
    assert bank_api.calls == [("cust-42", "card-7")]


@pytest.mark.asyncio
async def test_degrades_gracefully_on_bank_api_failure():
    tool = LockCardTool(FakeBankApiClient(should_fail=True), customer_id="cust-42")

    result = json.loads(await tool.run(card_id="card-7"))

    assert "error" in result


def test_requires_authentication():
    assert LockCardTool.requires_authentication is True
