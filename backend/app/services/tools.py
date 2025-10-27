"""Tool definitions and execution helpers."""

from datetime import datetime
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

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
            "name": "search_web",
            "description": "Search the web for current information, news, facts, or any knowledge that requires up-to-date data. Use this when you need real-time information or recent events.",
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
    elif tool_name == "search_web":
        return execute_search_web(tool_input)
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


def execute_search_web(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a web-search-capable LLM with automatic fallback.

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

    # Construct the search prompt.
    search_prompt = f"""Search the web for the following request and provide detailed, accurate information:

{query}

Requirements:
1. Provide up-to-date, accurate information
2. List primary sources when multiple exist
3. Note the time of the information when relevant
4. Present results in a clear, structured format"""

    # Try each configured model until one succeeds.
    last_error = None
    for model_id in config.WEB_SEARCH_MODELS:
        try:
            result = call_search_llm(search_prompt, model_id)
            return {"success": True, "query": query, "result": result, "model_used": model_id}
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
        "message": "Suggestions: 1) Use another method to answer 2) Tell the user search is unavailable 3) Answer using existing knowledge",
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
