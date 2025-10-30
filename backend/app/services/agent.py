"""Core agent loop and persistence helpers."""

import asyncio
import base64
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import config
from app.models import File, FileImage, Message
from app.services.llm import call_llm_with_tools
from app.services.tools import execute_tool
from app.utils.helpers import get_timestamp, sse_event

ASSISTANT_ARTIFACT_TOOL_NAME = "__assistant_artifact__"


class MultipleToolCallsError(Exception):
    """Raised when the model requests more than one tool call at once."""


class UnexpectedFinishReasonError(Exception):
    """Raised when the OpenAI finish_reason is not recognized."""


def load_complete_history(session_id: int, db: Session) -> List[Dict[str, Any]]:
    """Return the ordered message history for a session.

    Args:
        session_id: Identifier of the chat session.
        db: Database session used for queries.

    Returns:
        List[Dict[str, Any]]: History formatted for the OpenAI API.
    """
    messages = db.query(Message).filter(Message.session_id == session_id).order_by(Message.sequence).all()

    history = []
    for msg in messages:
        if msg.role == "user":
            # User messages may contain both text and images.
            if msg.content:
                content_data = json.loads(msg.content)
                history.append({"role": "user", "content": content_data})
        elif msg.role == "assistant":
            if msg.tool_call_id:
                # Assistant tool calls include serialized arguments.
                tool_input = json.loads(msg.tool_input) if msg.tool_input else {}
                history.append(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": msg.tool_call_id,
                                "type": "function",
                                "function": {"name": msg.tool_name, "arguments": json.dumps(tool_input)},
                            }
                        ],
                    }
                )
            elif msg.tool_name != ASSISTANT_ARTIFACT_TOOL_NAME:
                assistant_content = msg.content or ""
                assistant_parsed: Dict[str, Any] | List[Dict[str, Any]] | None = None
                try:
                    parsed = json.loads(assistant_content)
                    if isinstance(parsed, dict) and parsed.get("type") == "assistant_final":
                        assistant_parsed = parsed  # store for progress if needed later
                    elif isinstance(parsed, list):
                        assistant_parsed = parsed
                except (json.JSONDecodeError, TypeError):
                    assistant_parsed = None

                if isinstance(assistant_parsed, dict):
                    final_text = assistant_parsed.get("final", "")
                    history.append({"role": "assistant", "content": final_text})
                elif isinstance(assistant_parsed, list):
                    history.append({"role": "assistant", "content": assistant_parsed})
                else:
                    history.append({"role": "assistant", "content": assistant_content})
            else:
                assistant_content = msg.content or ""
                artifact_content: Optional[List[Dict[str, Any]]] = None
                try:
                    parsed = json.loads(assistant_content)
                    if isinstance(parsed, list):
                        artifact_content = parsed
                except (json.JSONDecodeError, TypeError):
                    artifact_content = None

                if artifact_content:
                    history.append({"role": "assistant", "content": artifact_content})
        elif msg.role == "tool":
            tool_output_raw = msg.tool_output or ""
            content_value: Any = tool_output_raw
            try:
                parsed_output = json.loads(tool_output_raw) if tool_output_raw else None
            except json.JSONDecodeError:
                parsed_output = None

            if isinstance(parsed_output, dict):
                content_value = build_tool_message_content(parsed_output)

            history.append({"role": "tool", "tool_call_id": msg.tool_call_id, "content": content_value})

    return history


def build_message_content_with_files(user_message: str, file_ids: List[int], db: Session) -> List[Dict[str, Any]]:
    """Construct a user message that inlines referenced files.

    Args:
        user_message: Text content provided by the user.
        file_ids: File identifiers to attach to the message.
        db: Database session used to fetch file metadata.

    Returns:
        List[Dict[str, Any]]: Message content containing text and image blocks.
    """
    content: List[Dict[str, Any]] = [{"type": "text", "text": user_message}]

    for file_id in file_ids:
        # Retrieve file metadata.
        file = db.query(File).filter(File.id == file_id).first()
        if not file:
            continue

        # Load images ordered by page.
        file_images = db.query(FileImage).filter(FileImage.file_id == file_id).order_by(FileImage.page_number).all()

        # Attach metadata plus encoded images for each page.
        for img in file_images:
            content.append({"type": "text", "text": f"\n[File: {file.filename}, Page {img.page_number}]"})

            image_base64 = base64.b64encode(img.image_data).decode("utf-8")
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{image_base64}", "detail": "high"}}
            )

    return content


def build_tool_file_message_content(file_id: int, header_text: str, db: Session) -> Optional[List[Dict[str, Any]]]:
    """Generate assistant message content for tool-generated files.

    Args:
        file_id: Identifier of the converted or downloaded file.
        header_text: Textual prefix describing the attachment.
        db: Database session used to fetch file metadata.

    Returns:
        Optional[List[Dict[str, Any]]]: Structured content containing text and images,
        or None when the file cannot be located or has no derived images.
    """
    file = db.query(File).filter(File.id == file_id).first()
    if file is None:
        return None

    file_images = db.query(FileImage).filter(FileImage.file_id == file_id).order_by(FileImage.page_number).all()
    if not file_images:
        return None

    content: List[Dict[str, Any]] = [{"type": "text", "text": header_text}]

    for image in file_images:
        content.append({"type": "text", "text": f"[File: {file.filename}, Page {image.page_number}]"})
        image_base64 = base64.b64encode(image.image_data).decode("utf-8")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/webp;base64,{image_base64}", "detail": "high"},
            }
        )

    return content


def save_user_message_to_db(session_id: int, content: List[Dict[str, Any]], sequence: int, db: Session) -> int:
    """Persist a user message and return its identifier.

    Args:
        session_id: Identifier of the owning session.
        content: Message payload including files.
        sequence: Sequence number within the session.
        db: Database session used for persistence.

    Returns:
        int: Primary key of the stored message.
    """
    message = Message(
        session_id=session_id, role="user", content=json.dumps(content, ensure_ascii=False), sequence=sequence
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message.id


def save_assistant_structured_message_to_db(
    session_id: int,
    content: List[Dict[str, Any]],
    sequence: int,
    db: Session,
    *,
    tool_call_id: Optional[str] = None,
    tool_name: Optional[str] = None,
) -> int:
    """Persist an assistant message that includes structured content such as images.

    Args:
        session_id: Identifier of the owning session.
        content: Structured assistant content in OpenAI chat format.
        sequence: Sequence number within the session.
        db: Database session used for persistence.
        tool_call_id: Optional identifier of the tool call that produced the content.
        tool_name: Optional tool name classification used for downstream filtering.

    Returns:
        int: Primary key of the stored message.
    """
    message = Message(
        session_id=session_id,
        role="assistant",
        content=json.dumps(content, ensure_ascii=False),
        sequence=sequence,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message.id


def save_assistant_message_to_db(
    session_id: int,
    content: str,
    sequence: int,
    model_id: str,
    db: Session,
    progress_segments: Optional[List[str]] = None,
) -> int:
    """Persist an assistant message and return its identifier.

    Args:
        session_id: Identifier of the owning session.
        content: Assistant response text.
        sequence: Sequence number within the session.
        model_id: Model used to generate the response.
        db: Database session used for persistence.
        progress_segments: Optional execution log entries produced while
            `ready_to_reply` was false.

    Returns:
        int: Primary key of the stored message.
    """
    payload = {
        "type": "assistant_final",
        "final": content,
        "progress": progress_segments or [],
    }
    message = Message(
        session_id=session_id,
        role="assistant",
        content=json.dumps(payload, ensure_ascii=False),
        sequence=sequence,
        model_id=model_id,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message.id


def save_tool_call_to_db(
    session_id: int,
    tool_call_id: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_output: Dict[str, Any],
    sequence: int,
    db: Session,
) -> tuple:
    """Persist both the assistant tool-call request and the tool result.

    Args:
        session_id: Identifier of the owning session.
        tool_call_id: Unique identifier assigned by the model.
        tool_name: Registered tool name.
        tool_input: Arguments passed to the tool.
        tool_output: Result returned by the tool.
        sequence: Sequence number for the assistant message.
        db: Database session used for persistence.

    Returns:
        tuple: Identifiers for the assistant tool call and tool response
        messages.
    """
    assistant_msg = Message(
        session_id=session_id,
        role="assistant",
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        tool_input=json.dumps(tool_input, ensure_ascii=False),
        sequence=sequence,
    )
    db.add(assistant_msg)

    tool_msg = Message(
        session_id=session_id,
        role="tool",
        tool_call_id=tool_call_id,
        tool_output=json.dumps(tool_output, ensure_ascii=False),
        sequence=sequence + 1,
    )
    db.add(tool_msg)

    db.commit()
    db.refresh(assistant_msg)
    db.refresh(tool_msg)

    return assistant_msg.id, tool_msg.id


def build_tool_message_content(tool_payload: Any) -> Any:
    """Convert a tool result into chat history content suitable for the LLM."""
    if isinstance(tool_payload, dict):
        image_blocks = tool_payload.get("image_blocks")
        sanitized = {key: value for key, value in tool_payload.items() if key != "image_blocks"}
        text_fragment = json.dumps(sanitized, ensure_ascii=False)
        if isinstance(image_blocks, list) and image_blocks:
            content_parts: List[Dict[str, Any]] = [{"type": "text", "text": text_fragment}]
            for block in image_blocks:
                if isinstance(block, dict):
                    content_parts.append(block)
            return content_parts
        return text_fragment
    if isinstance(tool_payload, str):
        return tool_payload
    if tool_payload is None:
        return ""
    return json.dumps(tool_payload, ensure_ascii=False)


async def run_agent_loop(
    session_id: int, user_message: str, model_id: str, files: Optional[List[int]], db: Session
) -> AsyncGenerator[str, None]:
    """Run the main agent loop and stream SSE events.

    Args:
        session_id: Identifier of the session being updated.
        user_message: Latest user message text.
        model_id: Model identifier to use.
        files: Optional list of referenced file IDs.
        db: Database session used for reads and writes.

    Yields:
        str: SSE-formatted messages conveying status updates and content.

    Raises:
        MultipleToolCallsError: If the model attempts concurrent tool calls.
        UnexpectedFinishReasonError: When the OpenAI API returns an unknown
        finish reason.
    """
    start_time = time.time()

    # Emit initial status.
    yield sse_event(
        {
            "type": "status",
            "status": "processing",
            "message": "Processing your request...",
            "timestamp": get_timestamp(),
        }
    )

    # 1. Load the full history.
    history = load_complete_history(session_id, db)

    # 2. Prepend the system prompt if missing.
    if not history or history[0].get("role") != "system":
        history.insert(0, {"role": "system", "content": config.SYSTEM_PROMPT})

    # 3. Incorporate file metadata/images into the user message.
    user_content = build_message_content_with_files(user_message, files or [], db)

    # 4. Compute the next sequence number.
    max_sequence = (
        db.query(Message.sequence).filter(Message.session_id == session_id).order_by(Message.sequence.desc()).first()
    )
    current_sequence = (max_sequence[0] if max_sequence else 0) + 1

    # 5. Persist the user message.
    save_user_message_to_db(session_id, user_content, current_sequence, db)
    current_sequence += 1

    # 6. Append the message to the in-memory history.
    history.append({"role": "user", "content": user_content})

    iteration = 0
    retry_count = 0
    ready_to_reply_guard = False
    last_stream_guard_state: Optional[bool] = None
    progress_segments: List[str] = []
    progress_buffer = ""
    ready_to_reply_reminder = (
        "During your most recent reasoning tool call, you set `ready_to_reply` to false, which means you do not yet have"
        " enough information for a final answer. Continue executing your plan, calling tools, or refining the plan instead"
        " of replying. If you believe the conversation is ready for a final response, call the reasoning tool again to"
        " review the evidence and set `ready_to_reply` to true; otherwise, keep executing the next step."
    )
    self_check_reminder_inserted = False

    def flush_progress_buffer() -> None:
        nonlocal progress_buffer, progress_segments
        stripped = progress_buffer.strip()
        if stripped:
            progress_segments.append(stripped)
        progress_buffer = ""

    def parse_textual_tool_calls(text: str) -> List[Dict[str, Any]]:
        stripped = text.strip()
        if not stripped:
            return []

        argument_hints: Dict[str, set[str]] = {
            "reasoning": {"thinking_focus", "specific_question"},
            "ddgs_search": {"query"},
            "ai_search_web": {"query"},
            "get_current_time": {"timezone"},
            "playwright_browse": {"url"},
        }

        def infer_tool_name(payload: Dict[str, Any]) -> Optional[str]:
            payload_keys = {str(k) for k in payload.keys()}
            for tool_key, required_keys in argument_hints.items():
                if tool_key == "ddgs_search" and payload_keys.intersection({"query", "queries"}):
                    return tool_key
                if required_keys.issubset(payload_keys):
                    return tool_key
            return None

        def try_parse(segment: str) -> Any:
            segment_stripped = segment.strip()
            if not segment_stripped:
                return None

            def load_candidate(candidate: str) -> Any:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None

            direct = load_candidate(segment_stripped)
            if direct is not None:
                return direct

            wrappers = [('"', '"'), ("'", "'"), ("(", ")")]
            for open_br, close_br in wrappers:
                if segment_stripped.startswith(open_br) and segment_stripped.endswith(close_br):
                    inner = segment_stripped[len(open_br) : -len(close_br)]
                    wrapped = load_candidate(inner)
                    if wrapped is not None:
                        return wrapped
                    segment_stripped = inner.strip()

            if segment_stripped and segment_stripped[0] not in "{[":
                trimmed_lead = load_candidate(segment_stripped[1:])
                if trimmed_lead is not None:
                    return trimmed_lead

            if segment_stripped and segment_stripped[-1] not in "}]":
                trimmed_tail = load_candidate(segment_stripped[:-1])
                if trimmed_tail is not None:
                    return trimmed_tail

            return None

        parsed_objects: List[Any] = []
        direct = try_parse(stripped)
        if direct is not None:
            if isinstance(direct, list):
                parsed_objects.extend(direct)
            else:
                parsed_objects.append(direct)
        else:
            segments = [line.strip().rstrip(",") for line in stripped.splitlines() if line.strip()]
            for segment in segments:
                parsed = try_parse(segment)
                if parsed is not None:
                    parsed_objects.append(parsed)

        normalized_calls: List[Dict[str, Any]] = []
        for obj in parsed_objects:
            if not isinstance(obj, dict):
                continue

            name = obj.get("name") or obj.get("tool_name") or obj.get("function")

            raw_arguments = None
            for key in ("arguments", "args", "input", "parameters", "payload"):
                if key in obj:
                    raw_arguments = obj[key]
                    break

            if raw_arguments is None:
                candidates = {k: v for k, v in obj.items() if k not in {"id", "type", "name", "tool_name", "function"}}
                raw_arguments = candidates or obj

            if not name and isinstance(raw_arguments, dict):
                inferred = infer_tool_name(raw_arguments)
                if inferred:
                    name = inferred

            if not name:
                continue

            if isinstance(raw_arguments, str):
                args_str = raw_arguments
            else:
                try:
                    args_str = json.dumps(raw_arguments, ensure_ascii=False)
                except TypeError:
                    continue

            normalized_calls.append(
                {"id": obj.get("id", ""), "type": "function", "function": {"name": name, "arguments": args_str}}
            )

        return normalized_calls

    force_reasoning_next = False

    pending_text_output = ""
    textual_calls_detected: List[Dict[str, Any]] = []

    def collect_output_segments(guard_state: bool, final: bool = False) -> List[str]:
        nonlocal pending_text_output, textual_calls_detected

        segments: List[str] = []
        while pending_text_output:
            newline_idx = pending_text_output.find("\n")
            segment: Optional[str] = None

            if newline_idx != -1:
                segment = pending_text_output[: newline_idx + 1]
                pending_text_output = pending_text_output[newline_idx + 1 :]
            elif final or not pending_text_output.strip().startswith(("{", "[")):
                segment = pending_text_output
                pending_text_output = ""
            else:
                break

            if segment is None or not segment:
                continue

            parsed = parse_textual_tool_calls(segment)
            if parsed:
                textual_calls_detected.extend(parsed)
            else:
                segments.append(segment)

        return segments

    while iteration < config.MAX_ITERATIONS:
        textual_calls_detected = []
        # Notify the client that the agent is thinking.
        yield sse_event(
            {"type": "thinking", "message": "Thinking about how to respond...", "timestamp": get_timestamp()}
        )

        # Invoke the LLM stream.
        response_chunks = []
        tool_calls_buffer = []
        finish_reason = None
        # Stream deltas in real time while also storing the full text.
        full_content = ""

        tool_choice = {"type": "function", "function": {"name": "reasoning"}} if force_reasoning_next else None

        async for chunk in call_llm_with_tools(history, model_id, stream=True, tool_choice=tool_choice):
            response_chunks.append(chunk)

            # Process streaming content.
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    delta_text = delta.content
                    current_guard = ready_to_reply_guard
                    pending_text_output += delta_text

                    segments_to_emit = collect_output_segments(current_guard)
                    for segment in segments_to_emit:
                        if last_stream_guard_state != current_guard:
                            message = (
                                "Sharing execution progress..." if current_guard else "Starting response generation..."
                            )
                            yield sse_event(
                                {
                                    "type": "content_start",
                                    "message": message,
                                    "timestamp": get_timestamp(),
                                    "guarded": current_guard,
                                }
                            )
                            last_stream_guard_state = current_guard

                        if current_guard:
                            progress_buffer += segment
                        else:
                            full_content += segment

                        yield sse_event(
                            {
                                "type": "content_delta",
                                "delta": segment,
                                "timestamp": get_timestamp(),
                                "guarded": current_guard,
                            }
                        )

                # Accumulate tool-call fragments.
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index >= len(tool_calls_buffer):
                            tool_calls_buffer.append(
                                {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                            )
                        if tc.id:
                            tool_calls_buffer[tc.index]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_buffer[tc.index]["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_buffer[tc.index]["function"]["arguments"] += tc.function.arguments

                # Track the finish reason as soon as it appears.
                if chunk.choices[0].finish_reason:
                    finish_reason = chunk.choices[0].finish_reason

        # Flush any remaining buffered text before evaluating finish_reason.
        pending_segments = collect_output_segments(ready_to_reply_guard, final=True)
        for segment in pending_segments:
            current_guard = ready_to_reply_guard
            if last_stream_guard_state != current_guard:
                message = "Sharing execution progress..." if current_guard else "Starting response generation..."
                yield sse_event(
                    {
                        "type": "content_start",
                        "message": message,
                        "timestamp": get_timestamp(),
                        "guarded": current_guard,
                    }
                )
                last_stream_guard_state = current_guard

            if current_guard:
                progress_buffer += segment
            else:
                full_content += segment

            yield sse_event(
                {
                    "type": "content_delta",
                    "delta": segment,
                    "timestamp": get_timestamp(),
                    "guarded": current_guard,
                }
            )

        # Treat missing finish_reason as "stop" when we already have content but no tool calls.
        if finish_reason is None and not tool_calls_buffer and full_content.strip():
            finish_reason = "stop"

        # Decide how to act on the streamed response.
        if finish_reason == "tool_calls" and tool_calls_buffer:
            # Enforce single-tool execution.
            if len(tool_calls_buffer) > 1:
                if retry_count >= config.MAX_RETRY_ON_MULTIPLE_TOOLS:
                    yield sse_event(
                        {
                            "type": "error",
                            "error_code": "MULTIPLE_TOOLS_MAX_RETRIES",
                            "error_message": f"Model kept invoking multiple tools after {config.MAX_RETRY_ON_MULTIPLE_TOOLS} retries",
                            "timestamp": get_timestamp(),
                        }
                    )
                    raise MultipleToolCallsError("Model called multiple tools after max retries")

                # Inform the client about the retry.
                retry_count += 1
                yield sse_event(
                    {
                        "type": "retry",
                        "reason": "multiple_tools_called",
                        "retry_count": retry_count,
                        "max_retries": config.MAX_RETRY_ON_MULTIPLE_TOOLS,
                        "message": f"Model invoked {len(tool_calls_buffer)} tools, retrying ({retry_count}/{config.MAX_RETRY_ON_MULTIPLE_TOOLS})...",
                        "timestamp": get_timestamp(),
                    }
                )

                # Append a warning and retry.
                history.append({"role": "system", "content": config.MULTIPLE_TOOLS_WARNING})
                continue

            # Share iteration progress.
            iteration += 1
            yield sse_event(
                {
                    "type": "iteration_info",
                    "current_iteration": iteration,
                    "max_iterations": config.MAX_ITERATIONS,
                    "message": f"Tool call iteration {iteration}",
                    "timestamp": get_timestamp(),
                }
            )

            # Execute the requested tool.
            tool_call = tool_calls_buffer[0]
            tool_call_id = tool_call["id"]
            tool_name = tool_call["function"]["name"]
            if isinstance(tool_name, str) and tool_name.startswith("functions."):
                tool_name = tool_name.split(".", 1)[1]
                tool_call["function"]["name"] = tool_name

            tool_arguments = tool_call["function"]["arguments"]

            try:
                tool_input = json.loads(tool_arguments)
            except json.JSONDecodeError:
                tool_input = {"raw": tool_arguments}

            # Emit the tool_call event.
            yield sse_event(
                {
                    "type": "tool_call",
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "timestamp": get_timestamp(),
                }
            )

            # Notify that tool execution has started.
            yield sse_event(
                {
                    "type": "tool_executing",
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "message": f"Executing tool {tool_name}...",
                    "timestamp": get_timestamp(),
                }
            )

            # Run the tool and capture success state.
            try:
                if tool_name in {"playwright_browse", "download_and_convert_file"}:
                    tool_result = await asyncio.to_thread(execute_tool, tool_name, tool_input, history, session_id)
                else:
                    tool_result = execute_tool(tool_name, tool_input, history, session_id)
                if isinstance(tool_result, dict) and "success" in tool_result:
                    tool_success = bool(tool_result.get("success"))
                else:
                    tool_success = True
            except Exception as e:
                tool_result = {"success": False, "error": str(e)}
                tool_success = False

            # Emit the tool_result event.
            yield sse_event(
                {
                    "type": "tool_result",
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_output": tool_result,
                    "success": tool_success,
                    "timestamp": get_timestamp(),
                }
            )

            # Persist tool activity.
            save_tool_call_to_db(session_id, tool_call_id, tool_name, tool_input, tool_result, current_sequence, db)
            current_sequence += 2  # assistant + tool

            # Extend the in-memory history for the next iteration.
            history.append({"role": "assistant", "tool_calls": [tool_call]})
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": build_tool_message_content(tool_result),
                }
            )

            assistant_artifact_content: Optional[List[Dict[str, Any]]] = None
            if isinstance(tool_result, dict):
                file_id_value = tool_result.get("file_id")
                if isinstance(file_id_value, int):
                    page_count = tool_result.get("page_count")
                    note_text = str(tool_result.get("note") or "Downloaded file")
                    metadata_parts = [f"file_id={file_id_value}"]
                    if isinstance(page_count, int) and page_count > 0:
                        metadata_parts.append(f"pages={page_count}")
                    header_suffix = f" ({', '.join(metadata_parts)})" if metadata_parts else ""
                    header = f"(tool) {note_text}{header_suffix}"
                    assistant_artifact_content = build_tool_file_message_content(file_id_value, header, db)
                    if assistant_artifact_content:
                        save_assistant_structured_message_to_db(
                            session_id,
                            assistant_artifact_content,
                            current_sequence,
                            db,
                            tool_call_id=tool_call_id,
                            tool_name=ASSISTANT_ARTIFACT_TOOL_NAME,
                        )
                        current_sequence += 1

            if assistant_artifact_content:
                history.append({"role": "assistant", "content": assistant_artifact_content})

            if tool_name == "reasoning":
                ready_flag = None
                if isinstance(tool_result, dict):
                    ready_flag = tool_result.get("ready_to_reply")
                    if ready_flag and not self_check_reminder_inserted:
                        reminder = getattr(config, "SELF_CHECK_FINAL_RESPONSE_PROMPT", "")
                        if reminder:
                            history.append({"role": "system", "content": reminder})
                            self_check_reminder_inserted = True
                if ready_flag is False:
                    ready_to_reply_guard = True
                    last_stream_guard_state = None
                    if not history or history[-1].get("content") != ready_to_reply_reminder:
                        history.append({"role": "system", "content": ready_to_reply_reminder})
                elif ready_flag is True:
                    flush_progress_buffer()
                    ready_to_reply_guard = False
                    last_stream_guard_state = None

            retry_count = 0  # Reset retry count.
            force_reasoning_next = False

        elif finish_reason == "stop":
            textual_calls = textual_calls_detected
            if textual_calls:
                retry_count += 1
                if retry_count > config.MAX_RETRY_ON_MULTIPLE_TOOLS:
                    yield sse_event(
                        {
                            "type": "error",
                            "error_code": "TEXTUAL_TOOL_CALL_MAX_RETRIES",
                            "error_message": (
                                "Model repeatedly emitted raw JSON tool calls without using the structured tool-call channel."
                            ),
                            "timestamp": get_timestamp(),
                        }
                    )
                    raise MultipleToolCallsError("Model emitted raw JSON tool calls after max retries")

                reminder_message = (
                    "You did not invoke the tool via the structured tool-call channel. "
                    "Please regenerate your response using the proper tool call format, "
                    "and do not output JSON directly in the text. Only one tool call is allowed per turn."
                )

                yield sse_event(
                    {
                        "type": "retry",
                        "reason": "textual_tool_call",
                        "retry_count": retry_count,
                        "max_retries": config.MAX_RETRY_ON_MULTIPLE_TOOLS,
                        "message": reminder_message,
                        "timestamp": get_timestamp(),
                    }
                )

                history.append({"role": "system", "content": reminder_message})
                textual_calls_detected = []
                force_reasoning_next = True
                continue

            # Guard against empty final responses.
            if not full_content.strip():
                retry_count += 1
                if retry_count > config.MAX_RETRY_ON_MULTIPLE_TOOLS:
                    yield sse_event(
                        {
                            "type": "error",
                            "error_code": "EMPTY_RESPONSE_MAX_RETRIES",
                            "error_message": "Model produced no usable content after multiple retries.",
                            "timestamp": get_timestamp(),
                        }
                    )
                    raise UnexpectedFinishReasonError("Empty response after retries")

                reminder_message = (
                    "Your previous response contained no usable text. "
                    "Please provide a natural-language answer or call an appropriate tool."
                )
                yield sse_event(
                    {
                        "type": "retry",
                        "reason": "empty_content",
                        "retry_count": retry_count,
                        "max_retries": config.MAX_RETRY_ON_MULTIPLE_TOOLS,
                        "message": reminder_message,
                        "timestamp": get_timestamp(),
                    }
                )
                history.append({"role": "system", "content": reminder_message})
                force_reasoning_next = True
                continue

            # Model produced a final answer; the stream already delivered deltas.
            if ready_to_reply_guard:
                flush_progress_buffer()
                last_stream_guard_state = None
                yield sse_event(
                    {
                        "type": "status",
                        "status": "awaiting_more_actions",
                        "message": "Reasoning marked the task as not ready for a final answer. Continue executing the plan.",
                        "timestamp": get_timestamp(),
                    }
                )
                if not history or history[-1].get("content") != ready_to_reply_reminder:
                    history.append({"role": "system", "content": ready_to_reply_reminder})
                continue

            # Persist the assistant message.
            flush_progress_buffer()
            message_id = save_assistant_message_to_db(
                session_id, full_content, current_sequence, model_id, db, progress_segments
            )
            force_reasoning_next = False

            # Signal that streaming is finished (no need to resend the text).
            yield sse_event({"type": "content_done", "timestamp": get_timestamp(), "guarded": False})

            # Emit the final done event.
            total_time_ms = int((time.time() - start_time) * 1000)
            yield sse_event(
                {
                    "type": "done",
                    "message_id": message_id,
                    "session_id": session_id,
                    "total_iterations": iteration,
                    "total_time_ms": total_time_ms,
                    "timestamp": get_timestamp(),
                }
            )
            break

        else:
            if finish_reason is None and not full_content and not tool_calls_buffer:
                retry_count += 1
                if retry_count > config.MAX_RETRY_ON_MULTIPLE_TOOLS:
                    yield sse_event(
                        {
                            "type": "error",
                            "error_code": "UNEXPECTED_FINISH_REASON",
                            "error_message": "Model produced no content or tool call after multiple retries.",
                            "timestamp": get_timestamp(),
                        }
                    )
                    raise UnexpectedFinishReasonError("finish_reason None after retries")

                reminder_message = (
                    "Your previous response contained no valid text or tool call. "
                    "Please call an appropriate tool or produce a natural-language answer."
                )
                yield sse_event(
                    {
                        "type": "retry",
                        "reason": "empty_finish_reason",
                        "retry_count": retry_count,
                        "max_retries": config.MAX_RETRY_ON_MULTIPLE_TOOLS,
                        "message": reminder_message,
                        "timestamp": get_timestamp(),
                    }
                )
                history.append({"role": "system", "content": reminder_message})
                continue

            yield sse_event(
                {
                    "type": "error",
                    "error_code": "UNEXPECTED_FINISH_REASON",
                    "error_message": f"Unexpected finish_reason: {finish_reason}",
                    "timestamp": get_timestamp(),
                }
            )
            raise UnexpectedFinishReasonError(f"Unexpected finish_reason: {finish_reason}")

    # Abort if the maximum iteration count is reached.
    if iteration >= config.MAX_ITERATIONS:
        yield sse_event(
            {
                "type": "error",
                "error_code": "MAX_ITERATIONS_REACHED",
                "error_message": f"Reached maximum iterations ({config.MAX_ITERATIONS}); aborting execution",
                "timestamp": get_timestamp(),
            }
        )
