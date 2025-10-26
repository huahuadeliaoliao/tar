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
            "description": """Deep thinking tool. Invoking this pauses execution, reviews the full conversation, completed work, and current status, then provides a structured summary to plan next steps.

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
    """Summarize the conversation and provide guidance without calling another model.

    Args:
        tool_input: Parameters describing the reasoning focus.
        messages_history: Full conversation history.
        session_id: Identifier of the session being analyzed.

    Returns:
        Dict[str, Any]: Structured reasoning summary and statistics.
    """
    thinking_focus = tool_input.get("thinking_focus", "task_planning")
    specific_question = tool_input.get("specific_question", "")

    # ========== Part 1: extract key information ==========

    # 1. Initial user goal.
    user_messages = [m for m in messages_history if m.get("role") == "user"]
    initial_goal = ""
    if user_messages:
        first_msg = user_messages[0]
        initial_goal = extract_text_content(first_msg.get("content", ""))

    # 2. Tool calls that have already executed.
    tool_calls = []
    for msg in messages_history:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tool_name = tc["function"]["name"]
                tool_input_str = tc["function"]["arguments"]
                tool_call_id = tc["id"]

                # Pair with the matching tool result.
                tool_result = next(
                    (m for m in messages_history if m.get("role") == "tool" and m.get("tool_call_id") == tool_call_id),
                    None,
                )

                result_content = ""
                success = True
                if tool_result:
                    result_content = tool_result.get("content", "")
                    # Detect failures when the payload encodes one.
                    if isinstance(result_content, str):
                        success = "error" not in result_content.lower() or "success" in result_content.lower()

                tool_calls.append(
                    {"name": tool_name, "input": tool_input_str, "output": result_content, "success": success}
                )

    # 3. Assistant responses (excluding tool calls).
    assistant_responses = []
    for msg in messages_history:
        if msg.get("role") == "assistant" and msg.get("content"):
            content = extract_text_content(msg["content"])
            if content and len(content) > 10:  # Ignore trivial snippets.
                assistant_responses.append(content[:200])  # Keep the first 200 characters.

    # 4. Most recent context (last three rounds).
    recent_context = []
    recent_user_msgs = user_messages[-3:] if len(user_messages) > 1 else []
    for msg in recent_user_msgs[1:]:  # Skip the first entry (already captured as initial_goal).
        content = extract_text_content(msg.get("content", ""))
        if content:
            recent_context.append(content)

    # ========== Part 2: build a structured summary ==========

    summary_parts = []

    # User goal.
    summary_parts.append(
        f"""## 📋 Initial user goal
{initial_goal if initial_goal else "(Not specified clearly)"}
"""
    )

    # Recent clarifications.
    if recent_context:
        summary_parts.append(
            f"""## 💬 Recent clarifications
{chr(10).join(f"- {ctx}" for ctx in recent_context)}
"""
        )

    # Completed work.
    if tool_calls:
        summary_parts.append(
            f"""## ✅ Actions taken ({len(tool_calls)} total)
{format_tool_history(tool_calls)}
"""
        )
    else:
        summary_parts.append(
            """## ✅ Actions taken
(No tool calls have been executed yet)
"""
        )

    # Current progress.
    successful_tools = len([tc for tc in tool_calls if tc["success"]])
    failed_tools = len([tc for tc in tool_calls if not tc["success"]])

    summary_parts.append(
        f"""## 📊 Current status
- Conversation turns: {len(user_messages)}
- Successful actions: {successful_tools}
- Failed actions: {failed_tools}
- Assistant replies: {len(assistant_responses)}
"""
    )

    # ========== Part 3: provide focus-specific guidance ==========

    guidance_templates = {
        "task_planning": """## 🎯 Planning guidance
Reflect on the information above:
1. What is the user's core objective?
2. What key steps are needed to reach it?
3. How do those steps depend on each other?
4. What should you do first?
5. What obstacles might appear and how will you handle them?

Draft a clear, actionable plan.""",
        "progress_review": """## 🔍 Progress review guidance
Consider the information above:
1. What has been completed? How effective was it?
2. How far are you from the user's goal?
3. Is progress on track with expectations?
4. Have you drifted from the original goal?
5. What is the most important next action?

Summarize progress and state the next step.""",
        "problem_analysis": """## 🔧 Problem analysis guidance
Use the details above to think through:
1. What specific problem occurred?
2. What is the root cause?
3. Which approaches have been tried and why did they fail?
4. What alternative solutions are possible?
5. Which option is most likely to succeed?

Analyze the problem and propose a solution.""",
        "task_decomposition": """## 📝 Task decomposition guidance
Based on the information:
1. How can you break this task into independent subtasks?
2. What is the goal of each subtask?
3. What dependencies exist between subtasks?
4. In what order should you execute them?
5. How will you verify each subtask is complete?

Turn the complex task into clear execution steps.""",
        "strategy_adjustment": """## 🔄 Strategy adjustment guidance
Reflect on the current situation:
1. What strategy are you using now?
2. Is the strategy effective? Why or why not?
3. Is there a better way to reach the goal?
4. What needs to change?
5. What is the revised strategy?

Reevaluate the strategy and plan improvements.""",
    }

    guidance = guidance_templates.get(thinking_focus, guidance_templates["task_planning"])

    # ========== Part 4: include the specific question ==========

    summary_parts.append(
        f"""## ❓ Question to consider
{specific_question}

{guidance}
"""
    )

    # ========== Part 5: assemble the final output ==========

    final_output = f"""# 🧠 Deep thinking moment

{chr(10).join(summary_parts)}

---

💡 **Tip**: Review the information above carefully and think before proceeding. For complex tasks, plan first and then execute step by step.
"""

    return {
        "success": True,
        "thinking_focus": thinking_focus,
        "specific_question": specific_question,
        "reasoning_summary": final_output,
        "stats": {
            "total_tool_calls": len(tool_calls),
            "successful_calls": successful_tools,
            "failed_calls": failed_tools,
            "user_interactions": len(user_messages),
        },
    }


def format_tool_history(tool_calls: List[Dict[str, Any]]) -> str:
    """Render a readable summary of tool calls.

    Args:
        tool_calls: Sequence of tool call entries containing metadata.

    Returns:
        str: Formatted lines describing the tool usage history.
    """
    if not tool_calls:
        return "(None)"

    lines = []
    for i, tc in enumerate(tool_calls, 1):
        status = "✅" if tc["success"] else "❌"
        lines.append(f"{i}. {status} {tc['name']}")

        # Parse inputs when possible.
        try:
            import json

            input_data = json.loads(tc["input"]) if isinstance(tc["input"], str) else tc["input"]
            input_str = ", ".join(f"{k}={v}" for k, v in input_data.items())
            lines.append(f"   Params: {input_str}")
        except Exception:
            lines.append(f"   Params: {tc['input']}")

        # Preview up to 100 characters of output.
        output_str = str(tc["output"])
        output_preview = output_str[:100] + ("..." if len(output_str) > 100 else "")
        lines.append(f"   Result: {output_preview}")
        lines.append("")

    return "\n".join(lines)


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
