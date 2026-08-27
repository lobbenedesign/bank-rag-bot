from __future__ import annotations

from openai import AsyncOpenAI


class OpenAiEmbedder:
    def __init__(self, client: AsyncOpenAI, model: str = "text-embedding-3-small") -> None:
        self._client = client
        self._model = model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]

    async def embed_query(self, text: str) -> list[float]:
        (result,) = await self.embed_documents([text])
        return result
