"""File-backed branch directory: real data, real answers — unlike
BankApiClient (an HTTP client to a core-banking system that doesn't exist
for a demo bank), this adapter's data source is exactly what a real bank
would supply: a list of its own branches, kept current by whoever manages
that file. `branches.json` here is sample/seed data for a fictional bank —
swap it for the real thing and the tool works unmodified.

Matching is a case-insensitive substring match across all fields, not
geocoded distance — "vicino a me" needs the customer's location, which a
text chatbot doesn't have without asking for it explicitly. This is an
honest, disclosed simplification, not a hidden one.
"""
from __future__ import annotations

import json
from pathlib import Path

from bank_rag.application.ports.branch_directory import Branch

_DEFAULT_DATA_PATH = Path(__file__).parent / "branches.json"


class StaticBranchDirectory:
    def __init__(self, data_path: Path = _DEFAULT_DATA_PATH) -> None:
        raw = json.loads(data_path.read_text(encoding="utf-8"))
        self._branches = [Branch(**entry) for entry in raw]

    async def search(self, query: str) -> list[Branch]:
        normalized = query.strip().lower()
        if not normalized:
            return self._branches
        return [
            branch
            for branch in self._branches
            if normalized in branch.city.lower()
            or normalized in branch.postal_code.lower()
            or normalized in branch.address.lower()
            or normalized in branch.name.lower()
        ]
