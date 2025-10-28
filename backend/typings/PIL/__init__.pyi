from __future__ import annotations

from typing import Any, Tuple

class _Image:
    width: int
    height: int
    mode: str
    size: Tuple[int, int]

    def convert(self, *args: Any, **kwargs: Any) -> "_Image": ...

    def resize(self, *args: Any, **kwargs: Any) -> "_Image": ...

    def save(self, *args: Any, **kwargs: Any) -> None: ...

    def split(self) -> Tuple[Any, ...]: ...


class _Resampling:
    LANCZOS: int


class _ImageModule:
    Resampling: _Resampling

    def open(self, *args: Any, **kwargs: Any) -> _Image: ...

    def new(self, *args: Any, **kwargs: Any) -> _Image: ...


Image = _ImageModule()
