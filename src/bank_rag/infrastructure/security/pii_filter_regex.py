"""Regex-based PII masking, applied before any text reaches a third-party LLM API.

Deliberately a separate, swappable adapter: a stricter deployment can replace
this with a Presidio/NER-based filter without touching the use case that
calls it, and it can be unit-tested in complete isolation.
"""
from __future__ import annotations

import re

_PATTERNS: dict[str, re.Pattern[str]] = {
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    "card_number": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "codice_fiscale": re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPRST]\d{2}[A-Z]\d{3}[A-Z]\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}


class RegexPiiFilter:
    def mask(self, text: str) -> str:
        masked = text
        for label, pattern in _PATTERNS.items():
            masked = pattern.sub(f"[REDACTED_{label.upper()}]", masked)
        return masked
