from __future__ import annotations

from typing import Protocol

from bank_rag.domain.entities import AuditEntry


class AuditLog(Protocol):
    """Append-only by construction: the port exposes no update/delete method
    at all, so nothing in the application layer can even attempt to mutate
    a past entry. The concrete adapter should additionally enforce this at
    the database level (a DB role without UPDATE/DELETE grants on the table).
    """

    async def record(self, entry: AuditEntry) -> None: ...
