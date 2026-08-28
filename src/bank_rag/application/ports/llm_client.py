from __future__ import annotations

from collections.abc import AsyncIterator
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


@dataclass(frozen=True)
class LLMStreamChunk:
    """One increment of a streamed completion. `is_final` marks the last
    chunk, which carries the fully-accumulated LLMResponse (content +
    resolved tool_calls) instead of a delta — callers need the complete
    response to decide whether the turn ended in tool calls or text, exactly
    like the non-streaming `complete()` path does.
    """

    content_delta: str
    is_final: bool
    response: LLMResponse | None = None  # populated only when is_final=True


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

    def stream_complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]: ...
