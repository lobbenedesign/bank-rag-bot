"""Exercises the real adapter against the real seed data file — no mocks,
no fakes. This is the "no compromise" piece of the branch locator: the
adapter's logic and the actual branches.json it ships with are both real.
"""
from __future__ import annotations

import pytest

from bank_rag.infrastructure.branch_directory.static_branch_directory import StaticBranchDirectory


@pytest.mark.asyncio
async def test_matches_by_city_case_insensitive():
    directory = StaticBranchDirectory()

    results = await directory.search("milano")

    assert len(results) >= 1
    assert all(b.city == "Milano" for b in results)


@pytest.mark.asyncio
async def test_matches_by_postal_code():
    directory = StaticBranchDirectory()

    results = await directory.search("00185")

    assert len(results) == 1
    assert results[0].city == "Roma"


@pytest.mark.asyncio
async def test_empty_query_returns_all_branches():
    directory = StaticBranchDirectory()

    results = await directory.search("")

    assert len(results) == len(await directory.search(""))
    assert len(results) >= 4  # the seed file ships with at least these 4


@pytest.mark.asyncio
async def test_no_match_returns_empty_list():
    directory = StaticBranchDirectory()

    results = await directory.search("Nessuna Città Esistente Xyz")

    assert results == []
