from __future__ import annotations

from typing import Any, Dict, TypeVar

T = TypeVar("T")

class BaseModel:
    model_config: Any

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def model_dump(self, *args: Any, **kwargs: Any) -> Dict[str, Any]: ...

ConfigDict = Dict[str, Any]

def Field(default: Any = ..., *args: Any, **kwargs: Any) -> Any: ...
