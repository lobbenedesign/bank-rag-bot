"""Regex-based first line of defense against prompt injection in uploaded documents.

Not a complete solution — a determined attacker can phrase an injection in
ways no regex catches. It exists to strip the common, low-effort patterns at
ingestion time so they never even reach the index, complementing (not
replacing) the "tool output is data" instruction in the agent's system prompt.
"""
from __future__ import annotations

import re

_INJECTION_PATTERNS = [
    re.compile(r"ignor[ae]\s+(le\s+)?istruzion[ei]\s+(precedent[ei]|di\s+sistema)", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+\w+", re.IGNORECASE),
    re.compile(r"^\s*system\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\bDAN\s+mode\b", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
]

_REDACTION = "[CONTENUTO RIMOSSO: possibile tentativo di prompt injection]"


class RegexPromptInjectionSanitizer:
    def sanitize(self, text: str) -> str:
        sanitized = text
        for pattern in _INJECTION_PATTERNS:
            sanitized = pattern.sub(_REDACTION, sanitized)
        return sanitized
