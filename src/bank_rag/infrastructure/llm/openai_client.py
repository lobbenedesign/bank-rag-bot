from __future__ import annotations

import json
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from bank_rag.application.ports.llm_client import LLMResponse, LLMStreamChunk, ToolCall


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

    async def stream_complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system_prompt}, *messages],
            tools=tools or None,
            temperature=0.1,
            stream=True,
        )

        content_parts: list[str] = []
        # OpenAI streams tool-call arguments as string fragments, keyed by
        # index (not id — the id often only arrives on the first fragment)
        # — they must be concatenated before the accumulated JSON is valid.
        tool_call_fragments: dict[int, dict[str, str]] = {}
        finish_reason = "stop"

        async for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta
            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta.content:
                content_parts.append(delta.content)
                yield LLMStreamChunk(content_delta=delta.content, is_final=False)

            for tc_delta in delta.tool_calls or []:
                fragment = tool_call_fragments.setdefault(tc_delta.index, {"id": "", "name": "", "arguments": ""})
                if tc_delta.id:
                    fragment["id"] = tc_delta.id
                if tc_delta.function and tc_delta.function.name:
                    fragment["name"] = tc_delta.function.name
                if tc_delta.function and tc_delta.function.arguments:
                    fragment["arguments"] += tc_delta.function.arguments

        tool_calls = [
            ToolCall(id=f["id"], name=f["name"], arguments=json.loads(f["arguments"]) if f["arguments"] else {})
            for f in tool_call_fragments.values()
        ]
        final_response = LLMResponse(
            content="".join(content_parts) or None, tool_calls=tool_calls, finish_reason=finish_reason
        )
        yield LLMStreamChunk(content_delta="", is_final=True, response=final_response)
