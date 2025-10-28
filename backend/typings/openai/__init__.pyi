from __future__ import annotations

from typing import Any

class _ChatCompletions:
    def create(self, *args: Any, **kwargs: Any) -> Any: ...


class _Chat:
    completions: _ChatCompletions


class AsyncOpenAI:
    chat: _Chat

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...


class OpenAI(AsyncOpenAI):
    ...
