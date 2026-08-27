from __future__ import annotations

from typing import Protocol


class QueryRewriter(Protocol):
    """Resolves a follow-up question into a standalone one using conversation
    history (e.g. "e quanto costa il bonifico?" -> "quanto costa il bonifico
    sul Conto Base"), before it is used for retrieval.

    Needed because RagSearchTool only ever sees the single `query` argument
    the LLM decides to pass when it calls the tool — without this explicit
    resolution step, retrieval quality on follow-up questions depends on the
    model spontaneously restating context in its tool call, which is
    inconsistent across models and prompts.
    """

    async def rewrite(self, history: list[dict[str, str]], question: str) -> str: ...
