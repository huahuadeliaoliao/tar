"""Explore-tool execution helpers for transient tool enablement."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from app.services.llm import call_llm_with_tools
from app.services.tools import (
    get_internal_tools,
    get_optional_tool_definitions,
    get_optional_tool_names,
)

EXPLORE_CACHE_TTL_SECONDS = 120


@dataclass
class ExploreCacheEntry:
    """Cached exploration result."""

    tools: List[str]
    reason: Optional[str]
    confidence: Optional[str]
    warnings: List[str]
    timestamp: float


@dataclass
class LoopContext:
    """Mutable state shared across a single run loop iteration."""

    session_id: int
    model_id: str
    transient_enabled_tools: Set[str] = field(default_factory=set)
    explore_cache: Dict[str, ExploreCacheEntry] = field(default_factory=dict)


def _make_cache_key(payload: Dict[str, Any]) -> str:
    normalized = {
        "task_summary": str(payload.get("task_summary", "")).strip(),
        "observed_outputs": sorted(str(item).strip() for item in payload.get("observed_outputs") or []),
        "blocking_constraints": sorted(str(item).strip() for item in payload.get("blocking_constraints") or []),
        "prior_tools_used": sorted(str(item).strip() for item in payload.get("prior_tools_used") or []),
    }
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)


def _build_system_prompt(optional_tool_defs: List[Dict[str, Any]]) -> str:
    lines = [
        "You are a tool curator assisting an autonomous agent.",
        "Your job is to review the current task summary and decide which optional tools (if any) should be enabled.",
        "You must always respond by calling the function tool `enable_tool` with your decision.",
        "",
        "Optional tools you may enable:",
    ]
    if optional_tool_defs:
        for tool in optional_tool_defs:
            function_def = tool["function"]
            name = function_def.get("name", "")
            description = function_def.get("description", "")
            parameters = json.dumps(function_def.get("parameters", {}), ensure_ascii=False, indent=2)
            lines.append(f"- {name}: {description}")
            for param_line in parameters.splitlines():
                lines.append(f"    {param_line}")
    else:
        lines.append("- (No optional tools are currently available.)")

    lines.extend(
        [
            "",
            "Rules:",
            "1. You must call `enable_tool` exactly once.",
            "2. If no extra tools are needed, call `enable_tool` with an empty list and explain why.",
            "3. Only select tools that meaningfully support the described task.",
            "4. Enabled tools are valid for the current iteration only, so keep the list minimal.",
        ]
    )
    return "\n".join(lines)


def _build_user_message(payload: Dict[str, Any]) -> str:
    lines = [
        "Task summary:",
        payload.get("task_summary", ""),
    ]

    observed = payload.get("observed_outputs") or []
    if observed:
        lines.append("")
        lines.append("Observed outputs or evidence:")
        for item in observed:
            lines.append(f"- {item}")

    constraints = payload.get("blocking_constraints") or []
    if constraints:
        lines.append("")
        lines.append("Blocking constraints or requirements:")
        for item in constraints:
            lines.append(f"- {item}")

    prior_tools = payload.get("prior_tools_used") or []
    if prior_tools:
        lines.append("")
        lines.append("Tools already tried:")
        for item in prior_tools:
            lines.append(f"- {item}")

    return "\n".join(lines)


async def run_explore_tool(
    model_id: str,
    payload: Dict[str, Any],
    loop_ctx: LoopContext,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Execute the explore tool and update loop context with newly enabled tools."""
    cache_key = _make_cache_key(payload)
    bypass_cache = bool(payload.get("force_refresh"))

    if not bypass_cache:
        cached = loop_ctx.explore_cache.get(cache_key)
        if cached and (time.time() - cached.timestamp) < EXPLORE_CACHE_TTL_SECONDS:
            loop_ctx.transient_enabled_tools.update(cached.tools)
            if cached.tools:
                history.append(
                    {
                        "role": "system",
                        "content": (
                            "Reusing cached exploration result: extra tools enabled for this iteration: "
                            f"{', '.join(cached.tools)} (reason: {cached.reason or 'unspecified'}). "
                            "These tools expire after this iteration."
                        ),
                    }
                )
            else:
                history.append(
                    {
                        "role": "system",
                        "content": "Reusing cached exploration result: no additional tools required for this iteration.",
                    }
                )
            return {
                "success": True,
                "enabled": list(cached.tools),
                "reason": cached.reason,
                "confidence": cached.confidence,
                "warnings": list(cached.warnings),
                "cached": True,
            }

    optional_defs = get_optional_tool_definitions(strip_meta=False)
    optional_names = get_optional_tool_names()
    system_prompt = _build_system_prompt(optional_defs)
    user_message = _build_user_message(payload)

    internal_tools = get_internal_tools()

    response = None
    async for chunk in call_llm_with_tools(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
        model_id=model_id,
        stream=False,
        tool_choice={"type": "function", "function": {"name": "enable_tool"}},
        tools_override=internal_tools,
    ):
        response = chunk

    if response is None or not getattr(response, "choices", None):
        history.append(
            {
                "role": "system",
                "content": "Tool exploration failed: the curator model did not return a decision. Continue with core tools.",
            }
        )
        return {
            "success": False,
            "error": "explore_no_response",
            "message": "The exploration helper did not return a decision.",
        }

    message = response.choices[0].message
    tool_calls = getattr(message, "tool_calls", None) or []
    if not tool_calls:
        history.append(
            {
                "role": "system",
                "content": "Tool exploration failed: enable_tool was not called. Adjust the request or continue without extra tools.",
            }
        )
        return {
            "success": False,
            "error": "missing_enable_tool_call",
            "message": "The exploration helper did not call enable_tool as required.",
        }

    enable_call = tool_calls[0]
    arguments = getattr(enable_call.function, "arguments", "") if enable_call.function else ""

    try:
        parsed_arguments = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        history.append(
            {
                "role": "system",
                "content": "Tool exploration failed: enable_tool arguments were invalid JSON. Provide clearer task details before retrying.",
            }
        )
        return {
            "success": False,
            "error": "invalid_enable_tool_payload",
            "message": "enable_tool arguments were not valid JSON.",
        }

    raw_tools = parsed_arguments.get("tools") or []
    selected_tools: List[str] = []
    invalid_tools: List[str] = []

    for tool_name in raw_tools:
        if isinstance(tool_name, str) and tool_name in optional_names:
            if tool_name not in selected_tools:
                selected_tools.append(tool_name)
        elif isinstance(tool_name, str):
            invalid_tools.append(tool_name)

    reason = parsed_arguments.get("reason")
    confidence = parsed_arguments.get("confidence")

    raw_warnings = parsed_arguments.get("warnings")
    if isinstance(raw_warnings, list):
        warnings = [str(item) for item in raw_warnings]
    elif raw_warnings is None:
        warnings = []
    else:
        warnings = [str(raw_warnings)]

    if invalid_tools:
        warnings = list(warnings) + [f"Ignored unknown tool: {name}" for name in invalid_tools]
        history.append(
            {
                "role": "system",
                "content": f"Explore tool ignored unknown tool names: {', '.join(invalid_tools)}.",
            }
        )

    loop_ctx.transient_enabled_tools.update(selected_tools)

    if selected_tools:
        reason_text = reason or "No reason provided"
        history.append(
            {
                "role": "system",
                "content": (
                    "Extra tools enabled for this iteration: "
                    f"{', '.join(selected_tools)} (reason: {reason_text}). "
                    "These tools expire after this iteration."
                ),
            }
        )
    else:
        history.append(
            {
                "role": "system",
                "content": "Explore tool determined no additional tools are required for this iteration.",
            }
        )

    cache_entry = ExploreCacheEntry(
        tools=list(selected_tools),
        reason=str(reason) if reason is not None else None,
        confidence=str(confidence) if confidence is not None else None,
        warnings=[str(item) for item in warnings],
        timestamp=time.time(),
    )
    loop_ctx.explore_cache[cache_key] = cache_entry

    return {
        "success": True,
        "enabled": list(selected_tools),
        "reason": cache_entry.reason,
        "confidence": cache_entry.confidence,
        "warnings": cache_entry.warnings,
        "cached": False,
    }
