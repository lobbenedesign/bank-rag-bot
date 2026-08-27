from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str


class LLMClient(Protocol):
    """Chat-completion port with native tool-calling.

    Kept provider-agnostic on purpose: swapping the OpenAI adapter for an
    Anthropic/local-model adapter never touches the agent orchestration logic.
    """

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse: ...
