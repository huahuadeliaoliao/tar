"""Tool definitions and execution helpers."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

from app.config import config
from app.services.ddgs_client import DDGSSearchError, get_ddgs_client

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"text", "images", "news", "videos", "books"}
SAFESEARCH_LEVELS = {"on", "moderate", "off"}
TIMELIMIT_VALUES = {"d", "w", "m", "y"}
LANG_TO_REGION = {
    "en": "us-en",
    "en-us": "us-en",
    "en-gb": "uk-en",
    "zh": "cn-zh",
    "zh-cn": "cn-zh",
    "zh-tw": "tw-tzh",
    "zh-hk": "hk-tzh",
    "es": "es-es",
    "es-mx": "mx-es",
    "fr": "fr-fr",
    "de": "de-de",
    "it": "it-it",
    "ja": "jp-jp",
    "ko": "kr-kr",
    "pt": "pt-pt",
    "pt-br": "br-pt",
    "ru": "ru-ru",
    "ar": "xa-ar",
    "hi": "in-en",
}
LOCATION_TO_REGION = {
    "united states": "us-en",
    "usa": "us-en",
    "china": "cn-zh",
    "mainland china": "cn-zh",
    "taiwan": "tw-tzh",
    "hong kong": "hk-tzh",
    "germany": "de-de",
    "france": "fr-fr",
    "italy": "it-it",
    "united kingdom": "uk-en",
    "uk": "uk-en",
    "japan": "jp-jp",
    "south korea": "kr-kr",
    "mexico": "mx-es",
    "spain": "es-es",
    "brazil": "br-pt",
    "india": "in-en",
    "canada": "ca-en",
    "canada-fr": "ca-fr",
    "australia": "au-en",
}
DEFAULT_MAX_RESULTS = 20


def _maybe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_region(region: Optional[str], location: Optional[str], lang: Optional[str], fallback: str) -> str:
    if isinstance(region, str) and region.strip():
        return region.strip().lower()

    if isinstance(location, str):
        key = location.strip().lower()
        if key in LOCATION_TO_REGION:
            return LOCATION_TO_REGION[key]

    if isinstance(lang, str):
        key = lang.strip().lower()
        if key in LANG_TO_REGION:
            return LANG_TO_REGION[key]
        if "-" in key:
            lang_part, country_part = key.split("-", 1)
            return f"{country_part}-{lang_part}"

    return fallback


def _filter_fields(result: Dict[str, Any], requested: Set[str] | None) -> Dict[str, Any]:
    if not requested or "*" in requested:
        return result

    allowed = set(requested) | {"rank", "backend"}
    return {key: value for key, value in result.items() if key in allowed}


def _format_results(
    raw_items: List[Dict[str, Any]],
    *,
    category: str,
    backend: str,
    requested_fields: Set[str] | None,
) -> List[Dict[str, Any]]:
    formatted: List[Dict[str, Any]] = []

    for idx, item in enumerate(raw_items, start=1):
        if category == "text":
            base = {
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", ""),
                "rank": idx,
                "backend": backend,
            }
        elif category == "images":
            base = {
                "title": item.get("title", ""),
                "image_url": item.get("image", ""),
                "thumbnail": item.get("thumbnail", ""),
                "page_url": item.get("url", ""),
                "source": item.get("source", ""),
                "width": _maybe_int(item.get("width")),
                "height": _maybe_int(item.get("height")),
                "rank": idx,
                "backend": backend,
            }
        elif category == "news":
            base = {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "snippet": item.get("body", ""),
                "date": item.get("date", ""),
                "image_url": item.get("image", ""),
                "rank": idx,
                "backend": backend,
            }
        elif category == "videos":
            base = {
                "title": item.get("title", ""),
                "url": item.get("content") or item.get("embed_url", ""),
                "description": item.get("description", ""),
                "duration": item.get("duration", ""),
                "provider": item.get("provider", ""),
                "publisher": item.get("publisher", ""),
                "embed_url": item.get("embed_url", ""),
                "thumbnails": item.get("images", {}),
                "rank": idx,
                "backend": backend,
            }
        elif category == "books":
            base = {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "author": item.get("author", ""),
                "publisher": item.get("publisher", ""),
                "info": item.get("info", ""),
                "thumbnail": item.get("thumbnail", ""),
                "rank": idx,
                "backend": backend,
            }
        else:  # pragma: no cover - safeguarded by category validation
            base = {"rank": idx, "backend": backend}

        formatted.append(_filter_fields(base, requested_fields))

    return formatted

# Tool definitions.
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time. You can optionally specify a timezone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Timezone name (e.g., 'Asia/Shanghai', 'America/New_York', 'UTC'). Defaults to 'UTC'.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ddgs_search",
            "description": (
                "Search the live web via DDGS metasearch. Provide focused queries, optionally specify category/backends, "
                "and call repeatedly to cover complex information needs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "One or more search queries. Each item should focus on a single intent.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Convenience alias when only one query is needed.",
                    },
                    "category": {
                        "type": "string",
                        "enum": sorted(VALID_CATEGORIES),
                        "description": "Search domain: text, images, news, videos, or books. Defaults to text.",
                    },
                    "backend": {
                        "type": "string",
                        "description": "Backend list (comma-separated) or 'auto' to let DDGS pick engines.",
                    },
                    "region": {
                        "type": "string",
                        "description": "Explicit region code like 'us-en'. Overrides lang/location heuristics.",
                    },
                    "lang": {
                        "type": "string",
                        "description": "Language hint used to infer region when explicit region is absent.",
                    },
                    "location": {
                        "type": "string",
                        "description": "Location hint (country/city) used to infer region when provided.",
                    },
                    "safesearch": {
                        "type": "string",
                        "enum": sorted(SAFESEARCH_LEVELS),
                        "description": "Safe-search level: on, moderate, or off.",
                    },
                    "timelimit": {
                        "type": "string",
                        "enum": sorted(TIMELIMIT_VALUES),
                        "description": "Time filter: d=day, w=week, m=month, y=year.",
                    },
                    "max_results": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 200,
                        "description": "Maximum number of results per query. Use non-positive values or omit for all available.",
                    },
                    "collect_per_result_fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Only include specific fields in each result. Use '*' to keep all.",
                    },
                    "include_raw": {
                        "type": "boolean",
                        "description": "Attach sanitized raw results for debugging/tracing.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional context describing the information need for logging/tracking.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ai_search_web",
            "description": (
                "Query an online-enabled language model that can browse the web. "
                "Use this only when ddgs_search is unavailable or insufficient, and validate important facts yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Detailed search query. Be specific and clear about what information you need.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reasoning",
            "description": """Deep thinking tool. Invoking this pauses execution, reviews the full conversation, completed work, and current status, then provides a structured summary to plan next steps. Treat it as your default first choice whenever the task feels complex, uncertain, or requires planning.

Best used when:
- The task is complex and needs planning before execution
- You are unsure about the next step
- You need to review completed vs. remaining work
- Execution is stuck and you must rethink strategy
- You must break down a multi-step task

You can call it multiple times for iterative planning.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "thinking_focus": {
                        "type": "string",
                        "enum": [
                            "task_planning",
                            "progress_review",
                            "problem_analysis",
                            "task_decomposition",
                            "strategy_adjustment",
                        ],
                        "description": "Thinking focus: task_planning=plan steps, progress_review=review progress, problem_analysis=analyze problems, task_decomposition=break down tasks, strategy_adjustment=adjust strategy",
                    },
                    "specific_question": {
                        "type": "string",
                        "description": 'Specific question to consider, e.g., "How should we implement auth next?", "Why did the previous step fail?", "How do we break down this task?"',
                    },
                },
                "required": ["thinking_focus", "specific_question"],
            },
        },
    },
]


def execute_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    messages_history: List[Dict[str, Any]] | None = None,
    session_id: int | None = None,
) -> Dict[str, Any]:
    """Dispatch a tool call to the corresponding implementation.

    Args:
        tool_name: Registered tool name.
        tool_input: JSON-serializable arguments passed by the model.
        messages_history: Conversation history to aid reasoning tools.
        session_id: Identifier of the chat session.

    Returns:
        Dict[str, Any]: Tool response payload.
    """
    if tool_name == "get_current_time":
        return execute_get_current_time(tool_input)
    elif tool_name == "ddgs_search":
        return execute_ddgs_search(tool_input)
    elif tool_name == "ai_search_web":
        return execute_ai_search_web(tool_input)
    elif tool_name == "reasoning":
        return execute_reasoning(tool_input, messages_history or [], session_id or 0)
    else:
        raise ValueError(f"Unknown tool: {tool_name}")


def execute_get_current_time(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Return the current time for an optional timezone.

    Args:
        tool_input: Dictionary that may include a `timezone` value.

    Returns:
        Dict[str, Any]: Structured time result including formatted output.
    """
    timezone_name = tool_input.get("timezone", "UTC")

    try:
        # Resolve the requested timezone.
        tz = ZoneInfo(timezone_name)
        now = datetime.now(tz)

        return {
            "success": True,
            "timezone": timezone_name,
            "datetime": now.isoformat(),
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "hour": now.hour,
            "minute": now.minute,
            "second": now.second,
            "weekday": now.strftime("%A"),
            "formatted": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Cannot get the time for timezone '{timezone_name}'. Use a valid timezone name (e.g., 'Asia/Shanghai', 'UTC').",
        }


def execute_ddgs_search(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Perform live web search using DDGS."""
    client = get_ddgs_client()

    raw_queries = tool_input.get("queries")
    if isinstance(raw_queries, str):
        raw_queries = [raw_queries]
    elif raw_queries is None:
        single_query = tool_input.get("query")
        raw_queries = [single_query] if single_query is not None else []
    elif not isinstance(raw_queries, list):
        raw_queries = []

    queries: List[str] = []
    for candidate in raw_queries:
        if isinstance(candidate, str):
            stripped = candidate.strip()
            if stripped:
                queries.append(stripped)

    if not queries:
        return {
            "success": False,
            "error": "empty_query",
            "message": "Provide at least one non-empty query in 'queries' or 'query'.",
        }

    category_default = config.DDGS_DEFAULT_CATEGORY if config.DDGS_DEFAULT_CATEGORY in VALID_CATEGORIES else "text"
    category = str(tool_input.get("category", category_default)).lower()
    if category not in VALID_CATEGORIES:
        category = category_default

    backend_default = config.DDGS_DEFAULT_BACKEND or "auto"
    backend_value = tool_input.get("backend", backend_default)
    backend = str(backend_value).strip() if isinstance(backend_value, str) else backend_default
    backend = backend or backend_default

    safesearch_default = (
        config.DDGS_DEFAULT_SAFESEARCH if config.DDGS_DEFAULT_SAFESEARCH in SAFESEARCH_LEVELS else "moderate"
    )
    safesearch_value = tool_input.get("safesearch", safesearch_default)
    safesearch = str(safesearch_value).lower() if isinstance(safesearch_value, str) else safesearch_default
    if safesearch not in SAFESEARCH_LEVELS:
        safesearch = safesearch_default

    timelimit_default = config.DDGS_DEFAULT_TIMELIMIT
    timelimit_value = tool_input.get("timelimit", timelimit_default)
    timelimit: str | None
    if isinstance(timelimit_value, str) and timelimit_value.strip():
        tl_candidate = timelimit_value.strip().lower()
        timelimit = tl_candidate if tl_candidate in TIMELIMIT_VALUES else None
    else:
        timelimit = None

    region_value = tool_input.get("region")
    region_override = region_value.strip() if isinstance(region_value, str) and region_value.strip() else None

    lang_value = tool_input.get("lang")
    lang = lang_value.strip() if isinstance(lang_value, str) and lang_value.strip() else None

    location_value = tool_input.get("location")
    location = location_value.strip() if isinstance(location_value, str) and location_value.strip() else None

    notes_value = tool_input.get("notes")
    notes = notes_value.strip() if isinstance(notes_value, str) and notes_value.strip() else None

    max_results_raw = tool_input.get("max_results")
    max_results: int | None = DEFAULT_MAX_RESULTS
    if isinstance(max_results_raw, int):
        if max_results_raw > 0:
            max_results = min(max_results_raw, 200)
        else:
            max_results = None
    elif isinstance(max_results_raw, str) and max_results_raw.strip().lower() in {"all", "none", "*", "unlimited"}:
        max_results = None

    fields_raw = tool_input.get("collect_per_result_fields")
    collect_fields: Set[str] | None = None
    if isinstance(fields_raw, list):
        collect_fields = {str(field).strip() for field in fields_raw if str(field).strip()}
        if not collect_fields or "*" in collect_fields:
            collect_fields = None

    include_raw = bool(tool_input.get("include_raw", False))

    region_fallback = config.DDGS_DEFAULT_REGION or "us-en"

    data_entries: List[Dict[str, Any]] = []
    overall_success = False

    for query in queries:
        resolved_region = _resolve_region(region_override, location, lang, region_fallback)

        try:
            result = client.search(
                query=query,
                category=category,
                backend=backend,
                region=resolved_region,
                safesearch=safesearch,
                timelimit=timelimit,
                max_results=max_results,
            )
        except DDGSSearchError as exc:
            failure_meta = {
                "query": query,
                "category": category,
                "backend": backend,
                "region": resolved_region,
                "safesearch": safesearch,
                "timelimit": timelimit,
                "cache_hit": False,
                "duration_ms": 0,
                "backend_list": [b.strip() for b in backend.split(",") if b.strip()] or [backend],
                "max_results_requested": max_results,
            }
            if notes:
                failure_meta["notes"] = notes

            data_entries.append(
                {
                    "query": query,
                    "success": False,
                    "error": exc.code,
                    "detail": exc.message,
                    "meta": failure_meta,
                }
            )

            logger.warning(
                "DDGS search failed",
                extra={
                    "ddgs_query": query,
                    "ddgs_error_code": exc.code,
                    "ddgs_backend": backend,
                    "ddgs_category": category,
                },
            )
            continue

        clean_items = [{k: v for k, v in item.items() if not str(k).startswith("_")} for item in result.items]
        formatted_results = _format_results(clean_items, category=category, backend=backend, requested_fields=collect_fields)

        meta: Dict[str, Any] = {
            "query": query,
            "category": category,
            "backend": backend,
            "backend_list": list(result.backend_list),
            "region": resolved_region,
            "safesearch": safesearch,
            "timelimit": timelimit,
            "result_count": len(formatted_results),
            "cache_hit": result.cache_hit,
            "duration_ms": result.duration_ms,
            "max_results_requested": max_results,
            "max_results_effective": result.max_results,
        }

        if collect_fields:
            meta["fields_included"] = sorted(collect_fields)
        if notes:
            meta["notes"] = notes
        if include_raw:
            meta["raw_results"] = clean_items

        data_entries.append(
            {
                "query": query,
                "success": True,
                "results": formatted_results,
                "meta": meta,
            }
        )

        overall_success = True

        logger.debug(
            "DDGS search succeeded",
            extra={
                "ddgs_query": query,
                "ddgs_result_count": len(formatted_results),
                "ddgs_cache_hit": result.cache_hit,
            },
        )

    response: Dict[str, Any] = {
        "success": overall_success,
        "category": category,
        "backend": backend,
        "safesearch": safesearch,
        "timelimit": timelimit,
        "queries": queries,
        "data": data_entries,
    }

    if not overall_success:
        response["error"] = "all_queries_failed"

    return response


def execute_ai_search_web(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a web-aware LLM as a fallback search mechanism.

    Args:
        tool_input: Dictionary that must include the `query`.

    Returns:
        Dict[str, Any]: Result payload indicating success and any content.
    """
    from app.config import config
    from app.services.llm import call_search_llm

    query = tool_input.get("query", "")

    if not query:
        return {"success": False, "error": "Search query cannot be empty"}

    # Construct the search prompt with reliability reminder.
    search_prompt = f"""Search the web for the following request and provide detailed, accurate information:

{query}

Requirements:
1. Provide up-to-date, accurate information
2. List primary sources when multiple exist
3. Note the time of the information when relevant
4. Present results in a clear, structured format
5. If information appears uncertain, state the confidence level and suggest verification steps"""

    # Try each configured model until one succeeds.
    last_error = None
    for model_id in config.WEB_SEARCH_MODELS:
        try:
            result = call_search_llm(search_prompt, model_id)
            return {
                "success": True,
                "query": query,
                "result": result,
                "model_used": model_id,
                "disclaimer": (
                    "This result comes from a browsing-capable language model. Verify critical details before use."
                ),
            }
        except Exception as e:
            last_error = str(e)
            # Log the error and continue.
            print(f"Search model {model_id} failed: {last_error}")
            continue

    # Every model failed.
    return {
        "success": False,
        "query": query,
        "error": "Unable to perform online search right now; all search services are unavailable",
        "detail": f"Last error: {last_error}" if last_error else "No search model configured",
        "message": (
            "Suggestions: 1) Prefer ddgs_search if possible 2) Tell the user online search is unavailable "
            "3) Answer using existing knowledge with caveats"
        ),
    }


def execute_reasoning(
    tool_input: Dict[str, Any], messages_history: List[Dict[str, Any]], session_id: int
) -> Dict[str, Any]:
    """Summarize the conversation and produce an execution plan without another model call.

    Args:
        tool_input: Parameters describing the reasoning focus.
        messages_history: Full conversation history.
        session_id: Identifier of the session being analyzed.

    Returns:
        Dict[str, Any]: Simplified reasoning output containing summary, plan, and readiness flag.
    """
    thinking_focus = tool_input.get("thinking_focus", "task_planning")
    specific_question = tool_input.get("specific_question", "")

    # Collect user messages for context.
    user_messages = [m for m in messages_history if m.get("role") == "user"]
    initial_goal = extract_text_content(user_messages[0].get("content", "")) if user_messages else ""

    # Track tool call history.
    tool_calls = []
    for msg in messages_history:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tool_call_id = tc["id"]
                tool_name = tc["function"]["name"]
                tool_input_str = tc["function"]["arguments"]

                tool_result = next(
                    (m for m in messages_history if m.get("role") == "tool" and m.get("tool_call_id") == tool_call_id),
                    None,
                )

                result_content = ""
                success = True
                if tool_result:
                    result_content = tool_result.get("content", "")
                    if isinstance(result_content, str):
                        lowered = result_content.lower()
                        success = not ("error" in lowered and "success" not in lowered)

                tool_calls.append(
                    {"name": tool_name, "input": tool_input_str, "output": result_content, "success": success}
                )

    # Build a concise textual summary with recent context and tool outcomes.
    summary_lines = []
    if initial_goal:
        summary_lines.append(f"User goal: {initial_goal}")
    if specific_question:
        summary_lines.append(f"Focus question: {specific_question}")

    if tool_calls:
        summary_lines.append(
            "Recent tool activity:\n" + "\n".join(format_tool_call_line(idx, tc) for idx, tc in enumerate(tool_calls, 1))
        )
    else:
        summary_lines.append("No tools have been used yet.")

    # Construct a high-level plan.
    plan = build_plan(thinking_focus, tool_calls, user_messages)

    # Decide whether the agent is ready to answer on the next turn.
    ready_to_reply = should_reply(tool_calls, plan)

    return {
        "success": True,
        "summary": "\n".join(summary_lines),
        "plan": plan,
        "ready_to_reply": ready_to_reply,
        "stats": {
            "total_tool_calls": len(tool_calls),
            "successful_calls": len([tc for tc in tool_calls if tc["success"]]),
            "failed_calls": len([tc for tc in tool_calls if not tc["success"]]),
            "user_interactions": len(user_messages),
        },
    }


def extract_text_content(content: Any) -> str:
    """Extract plain text from a mixed content payload.

    Args:
        content: Chat content which may be a string or list of parts.

    Returns:
        str: Concatenated text content.
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts)
    return ""


def get_available_tools() -> List[Dict[str, Any]]:
    """Return the tool definitions.

    Returns:
        List[Dict[str, Any]]: JSON-schema-compatible tool definitions.
    """
    return AVAILABLE_TOOLS


def format_tool_call_line(index: int, tool_call: Dict[str, Any]) -> str:
    """Render a single-line summary for a tool call."""
    status = "succeeded" if tool_call["success"] else "failed"
    return f"{index}. {tool_call['name']} ({status})"


def build_plan(thinking_focus: str, tool_calls: List[Dict[str, Any]], user_messages: List[Dict[str, Any]]) -> List[str]:
    """Construct a short execution plan based on focus and progress."""
    if not tool_calls and not user_messages:
        return ["Clarify the user goal.", "Identify the first action to take."]

    last_tool = tool_calls[-1] if tool_calls else None
    plan: List[str] = []

    if last_tool and not last_tool["success"]:
        plan.append("Diagnose why the last tool failed and adjust inputs or choose an alternative.")

    if last_tool and last_tool["success"]:
        plan.append("Incorporate the latest tool results and assess remaining information gaps.")

    focus_specific_steps = {
        "task_planning": [
            "Break the main objective into manageable steps.",
            "Execute the first pending step and reassess.",
        ],
        "progress_review": [
            "Summarize progress for the user.",
            "Highlight the most important next action based on remaining gaps.",
        ],
        "problem_analysis": [
            "Outline the root cause using gathered evidence.",
            "Select and execute the best solution path.",
        ],
        "task_decomposition": [
            "List key subtasks in order.",
            "Start executing the highest-priority subtask.",
        ],
        "strategy_adjustment": [
            "Assess current strategy effectiveness.",
            "Adjust the plan and implement the first change.",
        ],
    }

    plan.extend(focus_specific_steps.get(thinking_focus, ["Decide on the next best action and execute it."]))

    return plan


def should_reply(tool_calls: List[Dict[str, Any]], plan: List[str]) -> bool:
    """Determine whether the agent should reply to the user on the next turn."""
    if not tool_calls:
        return False

    last_tool = tool_calls[-1]
    if not last_tool["success"]:
        return False

    if not plan:
        return True

    plan_text = " ".join(plan).lower()
    actionable_keywords = ["execute", "start", "call", "retry", "diagnose", "adjust", "identify", "collect", "break"]

    if any(keyword in plan_text for keyword in actionable_keywords):
        return False

    return True
