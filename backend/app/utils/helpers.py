"""Utility helpers."""

import json
import time
from typing import Any, Dict


def sse_event(data: Dict[str, Any]) -> str:
    """Format data into a Server-Sent Events payload.

    Args:
        data: JSON-serializable payload to emit.

    Returns:
        str: SSE-formatted string containing the payload.
    """
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def get_timestamp() -> int:
    """Return the current Unix timestamp in seconds.

    Returns:
        int: Unix timestamp.
    """
    return int(time.time())


def format_file_size(size_bytes: int) -> str:
    """Convert a byte size into a human-readable string.

    Args:
        size_bytes: Size in bytes.

    Returns:
        str: Human-friendly representation with units.
    """
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
