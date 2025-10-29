from __future__ import annotations

from typing import Any

class HTTPAuthorizationCredentials:
    scheme: str
    credentials: str

class HTTPBearer:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def __call__(self, *args: Any, **kwargs: Any) -> HTTPAuthorizationCredentials: ...
