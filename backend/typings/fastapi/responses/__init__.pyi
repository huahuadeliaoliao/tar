from __future__ import annotations

from typing import Any, Optional

class Response:
    def __init__(self, content: Any = ..., media_type: Optional[str] = ..., headers: Optional[dict[str, str]] = ...) -> None: ...


class StreamingResponse(Response):
    def __init__(self, content: Any, media_type: Optional[str] = ..., headers: Optional[dict[str, str]] = ...) -> None: ...
