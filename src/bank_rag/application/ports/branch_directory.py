from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Branch:
    name: str
    address: str
    city: str
    postal_code: str
    phone: str
    opening_hours: str


class BranchDirectory(Protocol):
    """Not mocked, unlike BankApiClient: if the bank supplies real branch
    data (see infrastructure/branch_directory/), this port returns real
    answers — there is no "fake core banking system" problem here, just a
    dataset the bank owns and keeps current.
    """

    async def search(self, query: str) -> list[Branch]:
        """query is free text — a city, postal code, or partial address.
        Matching strategy is an adapter concern (substring, geocoded
        distance, etc.); the port only promises "branches matching query".
        """
        ...
