from typing import Any, BinaryIO


def load(__fp: BinaryIO, /) -> dict[str, Any]: ...


def loads(__data: str | bytes, /) -> dict[str, Any]: ...
