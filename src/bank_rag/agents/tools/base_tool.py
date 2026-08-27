"""Tool contract exposed to the LLM as a function-calling schema."""
from __future__ import annotations

from typing import Any, Protocol


class Tool(Protocol):
    name: str
    description: str
    parameters_schema: dict[str, Any]  # JSON Schema, passed verbatim to the LLM

    #: If True, only offered to authenticated conversations (e.g. balance lookup).
    requires_authentication: bool

    async def run(self, **kwargs: Any) -> str:
        """Executes the tool and returns a string the LLM can read back.
        Must never raise a raw exception up to the agent loop — catch and
        return a user-safe error string instead, since it becomes model input.
        """
        ...

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }
