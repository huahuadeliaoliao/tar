"""OpenAI API helpers."""

from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI

from app.config import config
from app.services.tools import get_available_tools

# Shared OpenAI client.
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)


async def call_llm_with_tools(
    messages: List[Dict[str, Any]],
    model_id: str,
    stream: bool = True,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncGenerator:
    """Call the chat API with tool support.

    Args:
        messages: Conversation history payload in OpenAI chat format.
        model_id: Identifier of the model to invoke.
        stream: Whether to stream the response.
        temperature: Optional override for sampling temperature.
        max_tokens: Optional override for maximum completion tokens.

    Yields:
        OpenAIStream or OpenAICompletion: Streaming chunks or a full response.
    """
    tools = get_available_tools()

    # Fall back to configured defaults when optional overrides are missing.
    if temperature is None:
        temperature = config.LLM_TEMPERATURE
    if max_tokens is None:
        max_tokens = config.LLM_MAX_TOKENS

    # Build the request payload.
    request_params = {
        "model": model_id,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "stream": stream,
        "temperature": temperature,
        "top_p": config.LLM_TOP_P,
        "frequency_penalty": config.LLM_FREQUENCY_PENALTY,
        "presence_penalty": config.LLM_PRESENCE_PENALTY,
    }

    # Only include max_tokens when a value is provided.
    if max_tokens is not None:
        request_params["max_tokens"] = max_tokens

    response = await client.chat.completions.create(**request_params)

    if stream:
        async for chunk in response:
            yield chunk
    else:
        yield response


async def call_llm_without_tools(messages: List[Dict[str, Any]], model_id: str, stream: bool = True) -> AsyncGenerator:
    """Call the chat API without tool support.

    Args:
        messages: Conversation history payload.
        model_id: Identifier of the model to invoke.
        stream: Whether to stream the response.

    Yields:
        OpenAIStream or OpenAICompletion: Streaming chunks or a full response.
    """
    response = await client.chat.completions.create(model=model_id, messages=messages, stream=stream)

    if stream:
        async for chunk in response:
            yield chunk
    else:
        yield response


def call_search_llm(prompt: str, model_id: str) -> str:
    """Invoke a synchronous model that can access the web.

    Args:
        prompt: Prompt instructing the model on the search task.
        model_id: Identifier of the search-capable model.

    Returns:
        str: Model response text.

    Raises:
        Exception: When the search model invocation fails.
    """
    from openai import OpenAI

    # Synchronous client used within tool execution.
    sync_client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)

    try:
        response = sync_client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            timeout=config.WEB_SEARCH_TIMEOUT,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        raise Exception(f"Model {model_id} call failed: {str(e)}") from e
