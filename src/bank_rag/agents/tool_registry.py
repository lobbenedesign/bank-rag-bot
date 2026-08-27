"""Composes the set of tools visible to the LLM for a given conversation state.

Access control lives here, not in the LLM's judgment: an unauthenticated
conversation physically never receives the balance-tool schema, so the model
cannot call it no matter how it's prompted.
"""
from __future__ import annotations

from bank_rag.agents.tools.base_tool import Tool


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {t.name: t for t in tools}

    def for_conversation(self, is_authenticated: bool) -> list[Tool]:
        return [
            t for t in self._tools.values()
            if is_authenticated or not t.requires_authentication
        ]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)
