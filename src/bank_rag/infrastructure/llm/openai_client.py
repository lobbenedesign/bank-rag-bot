from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from bank_rag.application.ports.llm_client import LLMResponse, ToolCall


class OpenAiChatClient:
    def __init__(self, client: AsyncOpenAI, model: str = "gpt-4.1-mini") -> None:
        self._client = client
        self._model = model

    async def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system_prompt}, *messages],
            tools=tools or None,
            temperature=0.1,
        )
        choice = response.choices[0]
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments))
            for tc in (choice.message.tool_calls or [])
        ]
        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
        )
