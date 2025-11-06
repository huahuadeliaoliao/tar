"""Helpers for filtering and exposing tool definitions."""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


class ToolRegistry:
    """Manage tool definitions with tier metadata and runtime filtering."""

    def __init__(self, tools: Sequence[Dict[str, Any]], internal_tools: Sequence[Dict[str, Any]]) -> None:
        """Store tool definitions and derive lookup structures."""
        self._tools: List[Dict[str, Any]] = list(tools)
        self._internal_tools: List[Dict[str, Any]] = list(internal_tools)
        self._tool_lookup: Dict[str, Dict[str, Any]] = {tool["function"]["name"]: tool for tool in self._tools}
        self._optional_tool_names: Set[str] = {
            name
            for name, tool in self._tool_lookup.items()
            if tool.get("tier") in {"extra", "mcp"} and tool.get("enablement", True)
        }

    @staticmethod
    def _strip_metadata(tool: Dict[str, Any]) -> Dict[str, Any]:
        stripped = copy.deepcopy(tool)
        stripped.pop("tier", None)
        stripped.pop("tags", None)
        stripped.pop("enablement", None)
        return stripped

    def core(self) -> List[Dict[str, Any]]:
        """Return all core tools with metadata removed."""
        return [
            self._strip_metadata(tool)
            for tool in self._tools
            if tool.get("tier") == "core" and tool.get("enablement", True)
        ]

    def for_session(self, transient_enabled: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        """Return tools visible during a run, including transient extras."""
        visible: List[Dict[str, Any]] = self.core()
        if not transient_enabled:
            return visible

        existing_names = {tool["function"]["name"] for tool in visible}
        for name in transient_enabled:
            tool = self._tool_lookup.get(name)
            if (
                tool
                and tool.get("enablement", True)
                and tool.get("tier") in {"extra", "mcp"}
                and name not in existing_names
            ):
                visible.append(self._strip_metadata(tool))
                existing_names.add(name)
        return visible

    def internal_tools(self) -> List[Dict[str, Any]]:
        """Return internal-only tool definitions (metadata stripped)."""
        return [self._strip_metadata(tool) for tool in self._internal_tools]

    def get_tools_by_tier(self, tiers: Iterable[str], *, strip_meta: bool = True) -> List[Dict[str, Any]]:
        """Return tools filtered by tier."""
        tier_set = set(tiers)
        selected = [tool for tool in self._tools if tool.get("tier") in tier_set and tool.get("enablement", True)]
        if strip_meta:
            return [self._strip_metadata(tool) for tool in selected]
        return [copy.deepcopy(tool) for tool in selected]

    def optional_tool_names(self) -> Set[str]:
        """Return names of tools that are not part of the core tier."""
        return set(self._optional_tool_names)
