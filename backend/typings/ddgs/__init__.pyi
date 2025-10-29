from __future__ import annotations

from typing import Any, Dict, List, Optional

class DDGS:
    threads: Optional[int]

    def __init__(self, proxy: Optional[str] = ..., timeout: Optional[int] = ..., verify: bool = ...) -> None: ...
    def text(
        self,
        query: str,
        *,
        region: str = ...,
        safesearch: str = ...,
        timelimit: Optional[str] = ...,
        max_results: Optional[int] = ...,
        backend: str = ...,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]: ...
    def images(
        self,
        query: str,
        *,
        region: str = ...,
        safesearch: str = ...,
        timelimit: Optional[str] = ...,
        max_results: Optional[int] = ...,
        backend: str = ...,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]: ...
    def news(
        self,
        query: str,
        *,
        region: str = ...,
        safesearch: str = ...,
        timelimit: Optional[str] = ...,
        max_results: Optional[int] = ...,
        backend: str = ...,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]: ...
    def videos(
        self,
        query: str,
        *,
        region: str = ...,
        safesearch: str = ...,
        timelimit: Optional[str] = ...,
        max_results: Optional[int] = ...,
        backend: str = ...,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]: ...
    def books(
        self,
        query: str,
        *,
        region: str = ...,
        safesearch: str = ...,
        timelimit: Optional[str] = ...,
        max_results: Optional[int] = ...,
        backend: str = ...,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]: ...

class TimeoutException(Exception): ...
class DDGSException(Exception): ...
