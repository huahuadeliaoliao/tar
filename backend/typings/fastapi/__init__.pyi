from __future__ import annotations

from typing import Any, Callable, Optional

class FastAPI:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class APIRouter:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def get(self, *args: Any, **kwargs: Any) -> Any: ...
    def post(self, *args: Any, **kwargs: Any) -> Any: ...
    def put(self, *args: Any, **kwargs: Any) -> Any: ...
    def delete(self, *args: Any, **kwargs: Any) -> Any: ...

class BackgroundTasks:
    def add_task(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None: ...

class UploadFile:
    filename: str
    content_type: Optional[str]

    async def read(self, *args: Any, **kwargs: Any) -> bytes: ...

class HTTPException(Exception):
    status_code: int
    detail: Any
    headers: Optional[dict[str, str]]

    def __init__(self, status_code: int, detail: Any = ..., headers: Optional[dict[str, str]] = ...) -> None: ...

def Depends(dependency: Any) -> Any: ...
def File(*args: Any, **kwargs: Any) -> Any: ...

class _Status:
    HTTP_200_OK = 200
    HTTP_201_CREATED = 201
    HTTP_400_BAD_REQUEST = 400
    HTTP_401_UNAUTHORIZED = 401
    HTTP_403_FORBIDDEN = 403
    HTTP_404_NOT_FOUND = 404
    HTTP_413_REQUEST_ENTITY_TOO_LARGE = 413

status = _Status()
