from __future__ import annotations

from typing import Any, Dict, Iterable


def encode(payload: Dict[str, Any], key: str, algorithm: str = ...) -> str: ...


def decode(token: str, key: str, algorithms: Iterable[str]) -> Dict[str, Any]: ...
