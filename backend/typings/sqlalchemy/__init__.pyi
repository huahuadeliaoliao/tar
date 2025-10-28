from __future__ import annotations

from typing import Any

class Column:
    ...


class DateTime:
    ...


class ForeignKey:
    ...


class Integer:
    ...


class LargeBinary:
    ...


class String:
    ...


class Text:
    ...


def create_engine(*args: Any, **kwargs: Any) -> Any: ...
