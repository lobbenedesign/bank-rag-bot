"""Finds bank branches by city/postal code/address. Unauthenticated (branch
addresses are public information) and needs no confirmation (read-only).
Mirrors RagSearchTool's tool-shape but talks to BranchDirectory instead of
the vector/keyword indexes — a different kind of "search", same pattern.
"""
from __future__ import annotations

import json
from typing import Any, ClassVar

from bank_rag.application.ports.branch_directory import BranchDirectory


class BranchLocatorTool:
    name = "find_branches"
    description = (
        "Finds the bank's physical branches near a city, postal code, or address the customer mentions. "
        "Use this when the customer asks where a branch is, or wants to visit one in person."
    )
    parameters_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "city, postal code, or address"}},
        "required": ["query"],
    }
    requires_authentication = False
    requires_confirmation = False

    def __init__(self, directory: BranchDirectory, max_results: int = 5) -> None:
        self._directory = directory
        self._max_results = max_results

    async def run(self, query: str) -> str:
        branches = await self._directory.search(query)
        if not branches:
            return json.dumps({"results": [], "note": "no branches found for this query"})
        return json.dumps(
            {
                "results": [
                    {
                        "name": b.name,
                        "address": b.address,
                        "city": b.city,
                        "postal_code": b.postal_code,
                        "phone": b.phone,
                        "opening_hours": b.opening_hours,
                    }
                    for b in branches[: self._max_results]
                ]
            }
        )

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }
