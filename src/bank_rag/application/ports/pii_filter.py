from __future__ import annotations

from typing import Protocol


class PiiFilter(Protocol):
    """Masks personal/sensitive data (IBAN, card numbers, fiscal codes) before
    any text leaves the process boundary towards a third-party LLM API.
    """

    def mask(self, text: str) -> str: ...
