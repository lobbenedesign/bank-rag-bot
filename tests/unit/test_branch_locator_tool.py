from __future__ import annotations

import json

import pytest

from bank_rag.agents.tools.branch_locator_tool import BranchLocatorTool
from bank_rag.application.ports.branch_directory import Branch


class FakeBranchDirectory:
    def __init__(self, branches: list[Branch]) -> None:
        self._branches = branches

    async def search(self, query: str) -> list[Branch]:
        return [b for b in self._branches if query.lower() in b.city.lower()]


def _branch(city: str) -> Branch:
    return Branch(name=f"Filiale {city}", address="Via Roma 1", city=city, postal_code="00100", phone="+39 06 000", opening_hours="9-17")


@pytest.mark.asyncio
async def test_returns_matching_branches():
    tool = BranchLocatorTool(FakeBranchDirectory([_branch("Milano"), _branch("Roma")]))

    result = json.loads(await tool.run(query="Milano"))

    assert len(result["results"]) == 1
    assert result["results"][0]["city"] == "Milano"


@pytest.mark.asyncio
async def test_no_results_returns_empty_list_not_an_error():
    tool = BranchLocatorTool(FakeBranchDirectory([_branch("Roma")]))

    result = json.loads(await tool.run(query="Palermo"))

    assert result["results"] == []


@pytest.mark.asyncio
async def test_caps_results_at_max_results():
    branches = [_branch("Milano") for _ in range(10)]
    tool = BranchLocatorTool(FakeBranchDirectory(branches), max_results=3)

    result = json.loads(await tool.run(query="Milano"))

    assert len(result["results"]) == 3


def test_no_authentication_or_confirmation_required():
    assert BranchLocatorTool.requires_authentication is False
    assert BranchLocatorTool.requires_confirmation is False
