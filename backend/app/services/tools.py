"""Tool definitions and execution helpers."""

import base64
import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from playwright.sync_api import Error as PlaywrightError

from app.config import config
from app.database import SessionLocal
from app.models import File, FileImage
from app.models import Session as SessionModel
from app.services.ddgs_client import DDGSSearchError, get_ddgs_client
from app.services.file_handler import (
    FileProcessingError,
    compress_image,
    convert_docx_ppt_to_images,
    convert_pdf_to_images,
)
from app.services.playwright_client import playwright_manager

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


def _persist_single_webp_image(
    session_id: int,
    filename: str,
    webp_bytes: bytes,
    width: int,
    height: int,
    *,
    file_type: str = "screenshot",
) -> int:
    """Store a single WebP image for the given session and return its file id."""
    db = SessionLocal()
    try:
        session_record = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session_record is None:
            raise ValueError(f"Session {session_id} not found")

        user_id = session_record.user_id
        new_file = File(
            user_id=user_id,
            filename=filename,
            file_type=file_type,
            mime_type="image/webp",
            file_data=webp_bytes,
            file_size=len(webp_bytes),
            processing_status="completed",
        )
        db.add(new_file)
        db.flush()

        file_image = FileImage(
            file_id=new_file.id,
            page_number=1,
            image_data=webp_bytes,
            width=width,
            height=height,
            file_size=len(webp_bytes),
        )
        db.add(file_image)
        db.commit()
        return new_file.id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


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
            "name": "playwright_browse",
            "description": (
                "Open a page, run optional actions, and extract text, attributes, HTML, or screenshots. A practical recipe is:\n"
                "  1. Probe the DOM with a lightweight `evaluate` or `count` call to inspect matching elements.\n"
                "  2. Once you know the structure, call `inner_text`, `all_inner_texts`, `attribute`, or `html` with the precise selector you need.\n"
                "  3. Use `keywords` or `page_range` only when you need to trim large results.\n"
                "You are free to mix these steps as needed—the tool simply returns what Playwright observes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Absolute URL to open.",
                    },
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle", "commit"],
                        "description": "Navigation readiness signal to wait for. Defaults to 'load'.",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Override navigation timeout in milliseconds.",
                    },
                    "actions": {
                        "type": "array",
                        "description": "Optional action list executed after navigation. Supported types: click, fill, wait_for_selector, wait_for_timeout.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["click", "fill", "wait_for_selector", "wait_for_timeout"],
                                },
                                "selector": {"type": "string"},
                                "value": {"type": ["string", "number", "boolean"]},
                                "button": {"type": "string", "enum": ["left", "middle", "right"]},
                                "click_count": {"type": "integer", "minimum": 1},
                                "force": {"type": "boolean"},
                                "state": {
                                    "type": "string",
                                    "enum": ["attached", "detached", "visible", "hidden"],
                                },
                                "duration_ms": {"type": "integer", "minimum": 0},
                            },
                            "required": ["type"],
                        },
                    },
                    "extract": {
                        "type": "array",
                        "description": (
                            "Extraction instructions executed after navigation. Supported types: inner_text, all_inner_texts, attribute, html, "
                            "outer_html, count, evaluate. Prefer probing selectors with `evaluate`/`count` first, then follow up with targeted "
                            "selector-based calls. Reserve `evaluate` for complex or fallback logic. html/outer_html results are converted to Markdown with length limits."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "inner_text",
                                        "all_inner_texts",
                                        "attribute",
                                        "html",
                                        "outer_html",
                                        "count",
                                        "evaluate",
                                    ],
                                },
                                "selector": {
                                    "type": "string",
                                    "description": (
                                        "Required for all types except 'evaluate'. Start broad only to probe the DOM; once you learn the structure, switch to a specific selector."
                                    ),
                                },
                                "name": {"type": "string"},
                                "attribute": {"type": "string"},
                                "expression": {"type": "string"},
                                "index": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "description": "When provided, operate on the nth matching element (0-based).",
                                },
                                "timeout_ms": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "description": "Override the timeout for this extraction only.",
                                },
                                "pick_first": {
                                    "type": "boolean",
                                    "description": "When true, automatically use the first matching element to avoid strict-mode violations.",
                                },
                                "keywords": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Optional keyword list. Only segments containing at least one keyword are kept.",
                                },
                                "page_range": {
                                    "description": "Optional page filter (e.g., '2-4' or [2,4]) for paginated content.",
                                    "oneOf": [
                                        {
                                            "type": "string",
                                            "description": "Single page like '3' or range '2-4'.",
                                        },
                                        {
                                            "type": "array",
                                            "items": {
                                                "type": "integer",
                                                "minimum": 1,
                                            },
                                            "minItems": 1,
                                            "maxItems": 2,
                                            "description": "Array of one or two positive integers, [start, end].",
                                        },
                                    ],
                                },
                            },
                            "required": ["type"],
                        },
                    },
                    "screenshot": {
                        "description": "Capture a screenshot. Use true for a viewport screenshot or provide an object with optional 'full_page' and 'selector'.",
                        "type": ["boolean", "object"],
                        "properties": {
                            "full_page": {"type": "boolean"},
                            "selector": {"type": "string"},
                        },
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "playwright_probe",
            "description": (
                "Open a page and quickly inspect one or more selectors. Returns match counts and small snippets so you can decide which selectors to use later."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Absolute URL to open for probing.",
                    },
                    "selectors": {
                        "description": "Selector string or array of selector strings to probe.",
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                            },
                        ],
                    },
                    "wait_until": {
                        "type": "string",
                        "enum": ["load", "domcontentloaded", "networkidle", "commit"],
                        "description": "Optional readiness state before probing. Defaults to 'load'.",
                    },
                    "timeout_ms": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Optional navigation timeout in milliseconds.",
                    },
                },
                "required": ["url", "selectors"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "download_and_convert_file",
            "description": (
                "Download a remote PDF, DOCX, or image file over HTTP(S), convert it into WebP images, and return the"
                " resulting pages for analysis. Invoke this only when you actually need to inspect the document contents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_url": {
                        "type": "string",
                        "description": "Direct HTTP(S) URL of the file to download.",
                    },
                    "file_type": {
                        "type": "string",
                        "enum": ["pdf", "docx", "image"],
                        "description": "Expected file type. Use 'pdf', 'docx', or 'image'.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional comments to log alongside the download request.",
                    },
                },
                "required": ["file_url", "file_type"],
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
            "description": """Reflect on the complete conversation and tool history without trimming. Use this whenever the
task feels complex, stalled, or uncertain. Before responding, pause execution and produce a concise JSON recap.

Best used when:
- You need to review the current goal, progress, and remaining gaps
- A previous step/tool failed or produced unexpected output
- New evidence (e.g., search/browse results) must be consolidated
- You are deciding whether it is safe to deliver the final answer

Always cover:
- Summary: current objective, what has been done, what still blocks you
- Evidence: confirmed facts or data points from searches/tools (include source + confidence when possible)
- Issues: recent failures, risks, or uncertainties that require attention
- Next actions: concrete, ordered steps you will take next
- Ready flag: set `ready_to_reply` to true only when you can answer the user without caveats

Even if you are ready to reply immediately, include a placeholder in `next_actions` (e.g., "Deliver final reply to the user").

Respond with structured JSON only; the system will not alter or add to your fields.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Concise recap of the current understanding, progress, and remaining concerns.",
                    },
                    "next_actions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Concrete next steps you plan to take. Each entry should be a single actionable item.",
                    },
                    "ready_to_reply": {
                        "type": "boolean",
                        "description": "Set to true only if you are prepared to deliver the final answer to the user.",
                    },
                    "evidence": {
                        "type": "array",
                        "description": "Confirmed facts from search/tool calls with optional source and confidence metadata.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "fact": {"type": "string"},
                                "source": {"type": "string"},
                                "confidence": {"type": "string"},
                            },
                            "required": ["fact"],
                        },
                    },
                    "issues": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Recent tool failures, risks, or uncertainties that still need attention.",
                    },
                    "confidence": {
                        "type": "string",
                        "description": "Optional confidence level or risk assessment for your current plan.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional additional remarks, dependencies, or reminders.",
                    },
                },
                "required": ["summary", "next_actions", "ready_to_reply"],
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
    elif tool_name == "playwright_browse":
        return execute_playwright_browse(tool_input, session_id)
    elif tool_name == "playwright_probe":
        return execute_playwright_probe(tool_input)
    elif tool_name == "download_and_convert_file":
        return execute_download_and_convert_file(tool_input, session_id)
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
        formatted_results = _format_results(
            clean_items, category=category, backend=backend, requested_fields=collect_fields
        )

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
    """Validate and echo the reasoning content provided by the primary model."""
    if not isinstance(tool_input, dict):
        return {
            "success": False,
            "error": "invalid_arguments",
            "detail": "Reasoning tool input must be an object.",
        }

    summary_raw = tool_input.get("summary")
    summary = str(summary_raw).strip() if summary_raw is not None else ""
    if not summary:
        return {
            "success": False,
            "error": "missing_summary",
            "detail": "Provide a non-empty 'summary' describing the current state.",
        }

    next_actions_raw = tool_input.get("next_actions")
    if isinstance(next_actions_raw, list):
        next_actions = [str(item).strip() for item in next_actions_raw if str(item).strip()]
    else:
        next_actions = []
        if next_actions_raw is not None:
            candidate = str(next_actions_raw).strip()
            if candidate:
                next_actions.append(candidate)

    if not next_actions:
        return {
            "success": False,
            "error": "missing_next_actions",
            "detail": "Include at least one action in 'next_actions', even if it is to proceed with the final reply.",
        }

    ready_value = tool_input.get("ready_to_reply")
    if isinstance(ready_value, bool):
        ready_to_reply = ready_value
    elif isinstance(ready_value, str):
        ready_to_reply = ready_value.strip().lower() in {"true", "1", "yes"}
    else:
        ready_to_reply = bool(ready_value)

    confidence_raw = tool_input.get("confidence")
    confidence = str(confidence_raw).strip() if confidence_raw is not None else None

    evidence_raw = tool_input.get("evidence")
    evidence: List[Dict[str, Any]] = []
    if isinstance(evidence_raw, list):
        for entry in evidence_raw:
            if isinstance(entry, dict):
                fact_raw = entry.get("fact")
                fact = str(fact_raw).strip() if fact_raw is not None else ""
                if not fact:
                    continue
                structured: Dict[str, Any] = {"fact": fact}
                source_raw = entry.get("source")
                confidence_raw = entry.get("confidence")
                if source_raw is not None:
                    structured["source"] = str(source_raw).strip()
                if confidence_raw is not None:
                    structured["confidence"] = str(confidence_raw).strip()
                evidence.append(structured)

    issues_raw = tool_input.get("issues")
    issues: List[str] = []
    if isinstance(issues_raw, list):
        issues = [str(item).strip() for item in issues_raw if str(item).strip()]

    notes_raw = tool_input.get("notes")
    notes = str(notes_raw).strip() if notes_raw is not None else None

    notes_raw = tool_input.get("notes")
    notes = str(notes_raw).strip() if notes_raw is not None else None

    payload: Dict[str, Any] = {
        "success": True,
        "summary": summary,
        "next_actions": next_actions,
        "ready_to_reply": ready_to_reply,
    }

    if confidence:
        payload["confidence"] = confidence
    if evidence:
        payload["evidence"] = evidence
    if issues:
        payload["issues"] = issues
    if notes:
        payload["notes"] = notes

    return payload


def execute_playwright_browse(tool_input: Dict[str, Any], session_id: Optional[int]) -> Dict[str, Any]:
    """Inspect a web page using the shared Playwright manager."""
    if not isinstance(tool_input, dict):
        return {
            "success": False,
            "error": "invalid_arguments",
            "detail": "Tool input must be an object.",
            "logs": [],
        }

    result = playwright_manager.browse(tool_input)
    if not isinstance(result, dict):
        return result

    screenshot_base64 = result.pop("screenshot_base64", None)
    screenshot_note = tool_input.get("notes")

    if screenshot_base64 and session_id not in (None, 0):
        warnings: List[str] = []
        try:
            png_bytes = base64.b64decode(screenshot_base64)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning("Failed to decode Playwright screenshot", exc_info=exc)
            warnings.append("screenshot_decode_failed")
            png_bytes = None

        file_id: Optional[int] = None
        if png_bytes:
            try:
                webp_bytes, width, height = compress_image(png_bytes, config.IMAGE_MAX_DIMENSION)
            except FileProcessingError as exc:
                logger.warning("Failed to process Playwright screenshot", exc_info=exc)
                warnings.append("screenshot_processing_failed")
            else:
                filename = tool_input.get("filename")
                if not isinstance(filename, str) or not filename.strip():
                    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
                    filename = f"playwright-screenshot-{timestamp}.webp"
                else:
                    filename = filename.strip()

                try:
                    file_id = _persist_single_webp_image(
                        session_id,
                        filename,
                        webp_bytes,
                        width,
                        height,
                        file_type="screenshot",
                    )
                except Exception as exc:  # pragma: no cover - persistence issues are environment-specific
                    logger.warning("Failed to persist Playwright screenshot", exc_info=exc)
                    warnings.append("screenshot_persistence_failed")
                else:
                    screenshot_meta = result.get("screenshot")
                    if isinstance(screenshot_meta, dict):
                        screenshot_meta.setdefault("width", width)
                        screenshot_meta.setdefault("height", height)
                        screenshot_meta["bytes"] = len(webp_bytes)
                    result["file_id"] = file_id
                    result["page_count"] = 1
                    if not screenshot_note:
                        final_url = result.get("final_url") or tool_input.get("url")
                        screenshot_note = (
                            f"Playwright screenshot for {final_url}" if final_url else "Playwright screenshot"
                        )
                    result["note"] = screenshot_note
                    result["truncated"] = False

        if warnings:
            result.setdefault("warnings", warnings)
    elif screenshot_base64:
        result.setdefault("warnings", []).append("screenshot_not_persisted")

    return result


def execute_playwright_probe(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Return selector probe information for a page without extracting full content."""
    return playwright_manager.probe_selectors(tool_input)


def execute_download_and_convert_file(tool_input: Dict[str, Any], session_id: Optional[int]) -> Dict[str, Any]:
    """Download a remote document and convert it to WebP images."""
    if session_id in (None, 0):
        return {
            "success": False,
            "error": "missing_session",
            "detail": "Session context is required to store converted files.",
        }

    if not isinstance(tool_input, dict):
        return {
            "success": False,
            "error": "invalid_arguments",
            "detail": "Tool input must be an object.",
        }

    file_url_raw = tool_input.get("file_url")
    file_type_raw = tool_input.get("file_type")

    if not isinstance(file_url_raw, str) or not file_url_raw.strip():
        return {
            "success": False,
            "error": "invalid_url",
            "detail": "Parameter 'file_url' must be a non-empty string.",
        }
    file_url = file_url_raw.strip()

    if not isinstance(file_type_raw, str) or not file_type_raw.strip():
        return {
            "success": False,
            "error": "invalid_file_type",
            "detail": "Parameter 'file_type' must be one of 'pdf', 'docx', or 'image'.",
        }

    file_type = file_type_raw.strip().lower()
    if file_type not in {"pdf", "docx", "image"}:
        return {
            "success": False,
            "error": "unsupported_file_type",
            "detail": "Supported file types are 'pdf', 'docx', and 'image'.",
        }

    parsed_url = urlparse(file_url)
    if parsed_url.scheme not in {"http", "https"}:
        return {
            "success": False,
            "error": "unsupported_scheme",
            "detail": "Only http and https URLs are supported for downloads.",
        }

    try:
        file_bytes, response_headers = playwright_manager.download_file(
            file_url, timeout=config.PLAYWRIGHT_NAVIGATION_TIMEOUT_MS
        )
    except PlaywrightError as exc:  # pragma: no cover - depends on runtime environment
        return {
            "success": False,
            "error": "download_failed",
            "detail": str(exc),
        }

    if not file_bytes:
        return {
            "success": False,
            "error": "empty_file",
            "detail": "Downloaded file was empty.",
        }

    max_size = max(config.PLAYWRIGHT_MAX_DOWNLOAD_SIZE_BYTES, 0)
    if max_size and len(file_bytes) > max_size:
        return {
            "success": False,
            "error": "file_too_large",
            "detail": (f"File size {len(file_bytes)} bytes exceeds the configured limit of {max_size} bytes."),
        }

    try:
        if file_type == "docx":
            images = convert_docx_ppt_to_images(file_bytes, "docx")
        elif file_type == "pdf":
            images = convert_pdf_to_images(file_bytes)
        else:
            compressed, width, height = compress_image(file_bytes, config.IMAGE_MAX_DIMENSION)
            images = [(compressed, width, height)]
    except FileProcessingError as exc:
        return {
            "success": False,
            "error": "conversion_failed",
            "detail": str(exc),
        }
    except Exception as exc:  # pragma: no cover - defensive guard
        return {
            "success": False,
            "error": "conversion_failed",
            "detail": str(exc),
        }

    if not images:
        return {
            "success": False,
            "error": "conversion_empty",
            "detail": "No images were produced during conversion.",
        }

    db = SessionLocal()
    try:
        session_record = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if session_record is None:
            return {
                "success": False,
                "error": "session_not_found",
                "detail": f"Session {session_id} was not found.",
            }

        user_id = session_record.user_id
        url_path = unquote(parsed_url.path or "")
        original_name = Path(url_path).name or f"downloaded.{file_type}"

        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, mode="w") as zip_file:
            for idx, (img_bytes, _, _) in enumerate(images, start=1):
                zip_file.writestr(f"page_{idx}.webp", img_bytes)
        archive_bytes = archive_buffer.getvalue()

        new_file = File(
            user_id=user_id,
            filename=original_name,
            file_type=f"converted_{file_type}",
            mime_type="application/zip",
            file_data=archive_bytes,
            file_size=len(archive_bytes),
            processing_status="completed",
        )
        db.add(new_file)
        db.flush()

        for idx, (img_bytes, width, height) in enumerate(images, start=1):
            file_image = FileImage(
                file_id=new_file.id,
                page_number=idx,
                image_data=img_bytes,
                width=width,
                height=height,
                file_size=len(img_bytes),
            )
            db.add(file_image)

        db.commit()
        file_id = new_file.id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    image_blocks: List[Dict[str, Any]] = []
    for img_bytes, _, _ in images:
        encoded = base64.b64encode(img_bytes).decode("utf-8")
        image_blocks.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/webp;base64,{encoded}",
                    "detail": "high",
                },
            }
        )

    metadata = {
        "original_file_name": original_name,
        "converted_pages": list(range(1, len(images) + 1)),
    }

    if response_headers:
        metadata["response_headers"] = response_headers

    notes_value = tool_input.get("notes")

    return {
        "success": True,
        "file_id": file_id,
        "page_count": len(images),
        "note": notes_value or f"Converted from {file_url}",
        "truncated": False,
        "image_blocks": image_blocks,
        "metadata": metadata,
    }


def get_available_tools() -> List[Dict[str, Any]]:
    """Return the tool definitions.

    Returns:
        List[Dict[str, Any]]: JSON-schema-compatible tool definitions.
    """
    return AVAILABLE_TOOLS
