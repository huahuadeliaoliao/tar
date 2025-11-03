"""Playwright manager used by tools to inspect live web pages."""

from __future__ import annotations

import atexit
import base64
import importlib
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import Browser, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.config import config

logger = logging.getLogger(__name__)

WAIT_UNTIL_OPTIONS = {"load", "domcontentloaded", "networkidle", "commit"}
SELECTOR_STATES = {"attached", "detached", "visible", "hidden"}

_html_converter: Optional[Any] = None
_html_converter_lock = threading.Lock()
_html_converter_import_error: Optional[str] = None
TRUNCATION_SUFFIX = "[...truncated...]"


class StrictModeViolation(RuntimeError):
    """Raised when a selector matches multiple elements in strict mode."""

    def __init__(self, selector: str, original_error: str) -> None:
        """Compose a helpful strict-mode error message."""
        suggestion = (
            "Selector matched multiple elements. Set 'pick_first': true, provide an 'index', "
            "or use a more specific selector (e.g., nth selector or xpath)."
        )
        message = f"Strict mode violation for selector '{selector}'. {suggestion}\n{original_error}"
        super().__init__(message)
        self.selector = selector
        self.original_error = original_error


def _get_html_converter() -> Optional[Any]:
    """Return a singleton MarkItDown HTML converter if available."""
    global _html_converter, _html_converter_import_error
    if _html_converter is not None:
        return _html_converter
    if _html_converter_import_error is not None:
        return None

    with _html_converter_lock:
        if _html_converter is not None:
            return _html_converter
        if _html_converter_import_error is not None:
            return None
        try:
            module = importlib.import_module("markitdown.converters._html_converter")
            converter_cls = getattr(module, "HtmlConverter", None)
            if converter_cls is None:
                raise AttributeError("HtmlConverter not found in markitdown.converters._html_converter")
            _html_converter = converter_cls()
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency guard
            _html_converter_import_error = str(exc)
            logger.debug("MarkItDown not installed; HTML extraction will remain raw.")
            return None
        except Exception as exc:  # pragma: no cover - defensive
            _html_converter_import_error = str(exc)
            logger.warning("Failed to initialise MarkItDown HtmlConverter", exc_info=exc)
            return None
    return _html_converter


def _parse_positive_int(value: Any) -> Optional[int]:
    """Return a positive integer parsed from ``value`` or ``None`` if invalid."""
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(float(value))
            return parsed if parsed > 0 else None
        except ValueError:
            return None
    return None


def _json_safe(value: Any) -> Any:
    """Return a JSON-serialisable representation of ``value``."""
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return str(value)


def _parse_non_negative_int(value: Any) -> Optional[int]:
    if isinstance(value, (int, float)) and value >= 0:
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(float(value))
            return parsed if parsed >= 0 else None
        except ValueError:
            return None
    return None


class PlaywrightManager:
    """Thread-safe wrapper around a single Playwright browser instance."""

    def __init__(self) -> None:
        """Set up synchronisation primitives and register shutdown hook."""
        self._lock = threading.Lock()
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._install_attempted = False
        browsers_path = os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", config.PLAYWRIGHT_BROWSERS_PATH)
        try:
            Path(browsers_path).mkdir(parents=True, exist_ok=True)
        except Exception:  # pragma: no cover - best effort
            logger.debug("Failed to ensure PLAYWRIGHT_BROWSERS_PATH exists", exc_info=True)
        atexit.register(self.shutdown)

    def shutdown(self) -> None:
        """Release Playwright resources."""
        with self._lock:
            self._close_browser_unlocked()

    def _close_browser_unlocked(self) -> None:
        if self._browser:
            try:
                self._browser.close()
            except Exception:  # pragma: no cover - best effort cleanup
                logger.debug("Failed to close Playwright browser", exc_info=True)
            finally:
                self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:  # pragma: no cover - best effort cleanup
                logger.debug("Failed to stop Playwright runtime", exc_info=True)
            finally:
                self._playwright = None

    def _ensure_browser(self) -> None:
        if self._playwright and self._browser:
            return
        logger.info("Starting Playwright headless browser instance")
        playwright = sync_playwright().start()
        self._playwright = playwright
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            if self._maybe_install_browsers(exc):
                browser = playwright.chromium.launch(headless=True)
            else:
                raise
        self._browser = browser

    def _restart_browser(self) -> None:
        logger.warning("Restarting Playwright browser after failure")
        self._close_browser_unlocked()
        self._ensure_browser()

    def _maybe_install_browsers(self, exc: PlaywrightError) -> bool:
        message = str(exc)
        if self._install_attempted:
            return False
        if "playwright install" not in message.lower():
            return False
        logger.info("Playwright browser executable missing; attempting automatic install...")
        self._install_attempted = True
        try:
            subprocess.run(
                ["python", "-m", "playwright", "install", "chromium", "--with-deps"],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("Playwright Chromium browser installed successfully.")
            return True
        except Exception:
            logger.exception("Automatic Playwright browser install failed")
            return False

    def browse(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Navigate to a URL, execute optional actions, and extract data."""
        logs: List[str] = []
        url = str(payload.get("url", "")).strip()
        if not url:
            return self._error("invalid_url", "Parameter 'url' is required.", logs)
        if url.lower().startswith("view-source:"):
            stripped = url[len("view-source:") :].strip()
            if not stripped:
                return self._error(
                    "invalid_url", "Parameter 'url' is required after stripping view-source: prefix.", logs
                )
            logs.append("view-source requested; using the rendered document instead.")
            url = stripped

        wait_until_candidate = str(payload.get("wait_until") or config.PLAYWRIGHT_DEFAULT_WAIT_UNTIL).strip().lower()
        wait_until = (
            wait_until_candidate if wait_until_candidate in WAIT_UNTIL_OPTIONS else config.PLAYWRIGHT_DEFAULT_WAIT_UNTIL
        )

        goto_timeout = _parse_positive_int(payload.get("timeout_ms")) or config.PLAYWRIGHT_NAVIGATION_TIMEOUT_MS
        actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
        extracts = payload.get("extract") if isinstance(payload.get("extract"), list) else []
        screenshot_option = payload.get("screenshot")

        if actions and len(actions) > config.PLAYWRIGHT_MAX_ACTIONS:
            return self._error(
                "too_many_actions",
                f"Received {len(actions)} actions but maximum allowed is {config.PLAYWRIGHT_MAX_ACTIONS}.",
                logs,
            )

        if extracts and len(extracts) > config.PLAYWRIGHT_MAX_EXTRACTIONS:
            return self._error(
                "too_many_extractions",
                f"Received {len(extracts)} extraction instructions but maximum allowed is {config.PLAYWRIGHT_MAX_EXTRACTIONS}.",
                logs,
            )

        for idx, extraction in enumerate(extracts, start=1):
            if not isinstance(extraction, dict):
                return self._error("invalid_extraction", f"Extraction {idx} must be an object with parameters.", logs)

            extraction_type = str(extraction.get("type", "")).strip().lower()

            if extraction_type != "evaluate":
                selector_value = extraction.get("selector")
                if not isinstance(selector_value, str) or not selector_value.strip():
                    return self._error(
                        "invalid_selector",
                        f"Extraction {idx} requires a non-empty 'selector'. Provide a precise CSS/XPath selector.",
                        logs,
                    )
                extraction["selector"] = selector_value.strip()

            try:
                keywords = self._normalize_keywords(extraction.get("keywords"))
            except ValueError as exc:
                return self._error("invalid_keywords", f"Extraction {idx}: {exc}", logs)
            if keywords:
                extraction["keywords"] = keywords
            elif "keywords" in extraction:
                extraction.pop("keywords", None)

            try:
                page_range = self._normalize_page_range(extraction.get("page_range"))
            except ValueError as exc:
                return self._error("invalid_page_range", f"Extraction {idx}: {exc}", logs)
            if page_range:
                extraction["page_range"] = list(page_range)
            elif "page_range" in extraction:
                extraction.pop("page_range", None)

        with self._lock:
            try:
                self._ensure_browser()
            except Exception as exc:  # pragma: no cover - launch failure is environment specific
                logger.exception("Failed to initialise Playwright browser")
                return self._error("browser_initialisation_failed", str(exc), logs)

            assert self._browser is not None  # for type checkers

            context = None
            page = None
            try:
                context = self._browser.new_context()
                page = context.new_page()
                context.set_default_timeout(config.PLAYWRIGHT_DEFAULT_TIMEOUT_MS)
                context.set_default_navigation_timeout(config.PLAYWRIGHT_NAVIGATION_TIMEOUT_MS)

                navigation_start = time.perf_counter()
                response = page.goto(url, wait_until=wait_until, timeout=goto_timeout)
                navigation_duration = int((time.perf_counter() - navigation_start) * 1000)
                status_code = response.status if response else None
                logs.append(
                    f"Navigated to {url} (status={status_code}, wait_until={wait_until}, duration={navigation_duration}ms)"
                )

                self._run_actions(page, actions, logs)
                extraction_results = self._run_extractions(page, extracts, logs)
                extraction_results = self._post_process_extractions(extraction_results, logs, page.url)
                screenshot_meta, screenshot_base64 = self._capture_screenshot_if_requested(
                    page, screenshot_option, logs
                )

                try:
                    title = page.title()
                except PlaywrightError:
                    title = ""

                result: Dict[str, Any] = {
                    "success": True,
                    "final_url": page.url,
                    "title": title,
                    "status_code": status_code,
                    "extractions": extraction_results,
                    "logs": logs,
                }
                if screenshot_meta:
                    result["screenshot"] = screenshot_meta
                if screenshot_base64:
                    result["screenshot_base64"] = screenshot_base64
                return result
            except PlaywrightTimeoutError as exc:
                logger.warning("Playwright operation timed out", exc_info=exc)
                return self._error("timeout", str(exc), logs)
            except StrictModeViolation as exc:
                logger.warning("Playwright strict mode violation", exc_info=exc)
                return self._error("strict_mode_violation", str(exc), logs)
            except PlaywrightError as exc:
                logger.warning("Playwright raised an error", exc_info=exc)
                self._restart_browser()
                return self._error("playwright_error", str(exc), logs)
            except ValueError as exc:
                return self._error("invalid_parameters", str(exc), logs)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Unexpected Playwright failure")
                self._restart_browser()
                return self._error("unexpected_error", str(exc), logs)
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception:  # pragma: no cover - defensive
                        logger.debug("Failed to close Playwright context", exc_info=True)

    def probe_selectors(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return match counts and sample snippets for selectors without extracting full content."""
        logs: List[str] = []
        url = str(payload.get("url", "")).strip()
        if not url:
            return self._error("invalid_url", "Parameter 'url' is required.", logs)
        wait_until_candidate = str(payload.get("wait_until") or config.PLAYWRIGHT_DEFAULT_WAIT_UNTIL).strip().lower()
        wait_until = (
            wait_until_candidate if wait_until_candidate in WAIT_UNTIL_OPTIONS else config.PLAYWRIGHT_DEFAULT_WAIT_UNTIL
        )

        raw_selectors = payload.get("selectors")
        selectors: List[str]
        if isinstance(raw_selectors, str):
            selectors = [raw_selectors.strip()]
        elif isinstance(raw_selectors, list):
            selectors = [str(item).strip() for item in raw_selectors if str(item).strip()]
        else:
            selectors = []

        if not selectors:
            return self._error(
                "invalid_selectors", "Parameter 'selectors' must be a non-empty string or array of strings.", logs
            )

        goto_timeout = _parse_positive_int(payload.get("timeout_ms")) or config.PLAYWRIGHT_NAVIGATION_TIMEOUT_MS

        with self._lock:
            try:
                self._ensure_browser()
            except Exception as exc:  # pragma: no cover - launch failure is environment specific
                logger.exception("Failed to initialise Playwright browser")
                return self._error("browser_initialisation_failed", str(exc), logs)

            assert self._browser is not None
            context = None
            page = None
            try:
                context = self._browser.new_context()
                page = context.new_page()
                context.set_default_timeout(config.PLAYWRIGHT_DEFAULT_TIMEOUT_MS)
                context.set_default_navigation_timeout(config.PLAYWRIGHT_NAVIGATION_TIMEOUT_MS)

                navigation_start = time.perf_counter()
                response = page.goto(url, wait_until=wait_until, timeout=goto_timeout)
                navigation_duration = int((time.perf_counter() - navigation_start) * 1000)
                status_code = response.status if response else None
                logs.append(
                    f"Navigated to {url} (status={status_code}, wait_until={wait_until}, duration={navigation_duration}ms)"
                )

                probes: List[Dict[str, Any]] = []
                for selector in selectors:
                    probe_result = self._probe_selector(page, selector)
                    probes.append({"selector": selector, "result": probe_result})

                try:
                    title = page.title()
                except PlaywrightError:
                    title = ""

                return {
                    "success": True,
                    "final_url": page.url,
                    "title": title,
                    "status_code": status_code,
                    "probes": probes,
                    "logs": logs,
                }
            except PlaywrightTimeoutError as exc:
                logger.warning("Playwright probe timed out", exc_info=exc)
                return self._error("timeout", str(exc), logs)
            except PlaywrightError as exc:
                logger.warning("Playwright raised an error during probe", exc_info=exc)
                self._restart_browser()
                return self._error("playwright_error", str(exc), logs)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Unexpected Playwright failure during probe")
                self._restart_browser()
                return self._error("unexpected_error", str(exc), logs)
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception:  # pragma: no cover - defensive
                        logger.debug("Failed to close Playwright context", exc_info=True)

    def _run_actions(self, page: Any, actions: List[Dict[str, Any]], logs: List[str]) -> None:
        """Execute user-specified actions sequentially."""
        if not actions:
            return

        for idx, action in enumerate(actions, start=1):
            if not isinstance(action, dict):
                raise ValueError(f"Action {idx} must be an object.")

            action_type = str(action.get("type", "")).strip().lower()
            if action_type == "click":
                selector = self._require_selector(action, context=f"action {idx}")
                logs.append(f"Action {idx}: click {selector}")
                locator = page.locator(selector)
                click_kwargs: Dict[str, Any] = {}
                button = str(action.get("button", "")).lower()
                if button in {"left", "middle", "right"}:
                    click_kwargs["button"] = button
                click_count = _parse_positive_int(action.get("click_count"))
                if click_count:
                    click_kwargs["click_count"] = click_count
                if action.get("force") is True:
                    click_kwargs["force"] = True
                locator.click(**click_kwargs)
            elif action_type == "fill":
                selector = self._require_selector(action, context=f"action {idx}")
                if "value" not in action:
                    raise ValueError(f"Action {idx} (fill) requires a 'value' field.")
                value = action["value"]
                logs.append(f"Action {idx}: fill {selector}")
                page.fill(selector, "" if value is None else str(value))
            elif action_type == "wait_for_selector":
                selector = self._require_selector(action, context=f"action {idx}")
                state = str(action.get("state", "")).strip().lower()
                state_value = state if state in SELECTOR_STATES else None
                logs.append(f"Action {idx}: wait_for_selector {selector} (state={state_value or 'visible'})")
                page.wait_for_selector(selector, state=state_value)
            elif action_type == "wait_for_timeout":
                duration = _parse_positive_int(action.get("duration_ms"))
                if duration is None:
                    raise ValueError(f"Action {idx} (wait_for_timeout) requires numeric 'duration_ms'.")
                logs.append(f"Action {idx}: wait_for_timeout {duration}ms")
                page.wait_for_timeout(duration)
            else:
                raise ValueError(f"Unsupported action type '{action_type}' for action {idx}.")

    def _select_target_locator(self, locator: Any, *, pick_first: bool, index: Optional[int]) -> Any:
        if index is not None:
            return locator.nth(index)
        if pick_first:
            return locator.first
        return locator

    def _run_extractions(self, page: Any, extracts: List[Dict[str, Any]], logs: List[str]) -> List[Dict[str, Any]]:
        """Collect data from the page after actions complete."""
        if not extracts:
            return []

        results: List[Dict[str, Any]] = []
        for idx, extraction in enumerate(extracts, start=1):
            if not isinstance(extraction, dict):
                raise ValueError(f"Extraction {idx} must be an object.")

            extraction_type = str(extraction.get("type", "")).strip().lower()
            name = extraction.get("name")
            entry: Dict[str, Any] = {"type": extraction_type}
            if isinstance(name, str) and name.strip():
                entry["name"] = name.strip()
            keywords_list = extraction.get("keywords")
            if isinstance(keywords_list, list) and keywords_list:
                entry["keywords"] = list(keywords_list)
            page_range_value = extraction.get("page_range")
            if isinstance(page_range_value, list) and len(page_range_value) == 2:
                entry["page_range"] = (int(page_range_value[0]), int(page_range_value[1]))

            metadata: Dict[str, Any] = {}

            if extraction_type == "evaluate":
                expression = extraction.get("expression")
                if not isinstance(expression, str) or not expression.strip():
                    raise ValueError(f"Extraction {idx} (evaluate) requires 'expression'.")
                logs.append(f"Extraction {idx}: evaluate JavaScript expression")
                value = page.evaluate(expression)
                entry["value"] = _json_safe(value)
                metadata["status"] = "ok"
            else:
                selector = self._require_selector(extraction, context=f"extraction {idx}")
                entry["selector"] = selector
                probe = self._probe_selector(page, selector)
                metadata["probe"] = probe

                if isinstance(probe, dict) and probe.get("error"):
                    entry["value"] = _json_safe(self._default_empty_value(extraction_type))
                    metadata["status"] = "invalid_selector"
                    metadata["message"] = f"Selector error: {probe['error']}"
                    entry["metadata"] = metadata
                    results.append(entry)
                    continue

                match_count = 0
                if isinstance(probe, dict):
                    match_count = int(probe.get("matched", 0)) if isinstance(probe.get("matched"), (int, float)) else 0
                metadata["match_count"] = match_count
                if match_count == 0:
                    entry["value"] = _json_safe(self._default_empty_value(extraction_type))
                    metadata["status"] = "no_match"
                    metadata["message"] = (
                        "Selector matched 0 elements. Use evaluate() or count to inspect the DOM before retrying."
                    )
                    entry["metadata"] = metadata
                    results.append(entry)
                    continue

                locator = page.locator(selector)
                pick_first = bool(extraction.get("pick_first", False))
                index_value = _parse_non_negative_int(extraction.get("index"))

                if extraction_type == "inner_text":
                    logs.append(f"Extraction {idx}: inner_text of {selector}")
                    target = self._select_target_locator(locator, pick_first=pick_first, index=index_value)
                    try:
                        value = target.inner_text()
                    except PlaywrightError as exc:
                        if "strict mode violation" in str(exc).lower() and not pick_first and index_value is None:
                            raise StrictModeViolation(selector, str(exc)) from exc
                        raise
                elif extraction_type == "all_inner_texts":
                    logs.append(f"Extraction {idx}: all_inner_texts of {selector}")
                    value = locator.all_inner_texts()
                elif extraction_type == "attribute":
                    attribute_name = extraction.get("attribute")
                    if not isinstance(attribute_name, str) or not attribute_name.strip():
                        raise ValueError(f"Extraction {idx} (attribute) requires 'attribute'.")
                    logs.append(f"Extraction {idx}: attribute '{attribute_name}' of {selector}")
                    target = self._select_target_locator(locator, pick_first=pick_first, index=index_value)
                    try:
                        value = target.get_attribute(attribute_name)
                    except PlaywrightError as exc:
                        if "strict mode violation" in str(exc).lower() and not pick_first and index_value is None:
                            raise StrictModeViolation(selector, str(exc)) from exc
                        raise
                elif extraction_type == "html":
                    logs.append(f"Extraction {idx}: inner_html of {selector}")
                    target = self._select_target_locator(locator, pick_first=pick_first, index=index_value)
                    try:
                        value = target.inner_html()
                    except PlaywrightError as exc:
                        if "strict mode violation" in str(exc).lower() and not pick_first and index_value is None:
                            raise StrictModeViolation(selector, str(exc)) from exc
                        raise
                elif extraction_type == "outer_html":
                    logs.append(f"Extraction {idx}: outer_html of {selector}")
                    target = self._select_target_locator(locator, pick_first=pick_first, index=index_value)
                    try:
                        value = target.evaluate("element => element.outerHTML")
                    except PlaywrightError as exc:
                        if "strict mode violation" in str(exc).lower() and not pick_first and index_value is None:
                            raise StrictModeViolation(selector, str(exc)) from exc
                        raise
                elif extraction_type == "count":
                    logs.append(f"Extraction {idx}: count of {selector}")
                    value = locator.count()
                else:
                    raise ValueError(f"Unsupported extraction type '{extraction_type}' for extraction {idx}.")

                entry["value"] = _json_safe(value)
                metadata["status"] = "ok" if not self._is_empty_extraction_result(extraction_type, value) else "empty"
                metadata["match_count"] = match_count

            if metadata:
                entry["metadata"] = metadata

            results.append(entry)

        return results

    def _probe_selector(self, page: Any, selector: str, sample_size: int = 3) -> Dict[str, Any]:
        try:
            probe = page.evaluate(
                """(params) => {
                    const { selector, sampleSize } = params || {};
                    let nodes;
                    try {
                        nodes = Array.from(document.querySelectorAll(selector));
                    } catch (error) {
                        return { error: error.message };
                    }
                    const samples = nodes.slice(0, sampleSize || 3).map(node => ({
                        outerHTML: node.outerHTML ? node.outerHTML.slice(0, 200) : "",
                        text: (node.textContent || "").trim().slice(0, 200),
                    }));
                    return { matched: nodes.length, samples };
                }""",
                {"selector": selector, "sampleSize": sample_size},
            )
        except PlaywrightError as exc:
            return {"error": str(exc)}

        if not isinstance(probe, dict):
            return {"error": "probe_failed"}

        matched = probe.get("matched")
        if not isinstance(matched, (int, float)):
            probe["matched"] = 0

        samples = probe.get("samples")
        if not isinstance(samples, list):
            probe["samples"] = []

        return probe

    @staticmethod
    def _default_empty_value(extraction_type: str) -> Any:
        if extraction_type == "all_inner_texts":
            return []
        if extraction_type == "count":
            return 0
        if extraction_type == "attribute":
            return None
        return ""

    @staticmethod
    def _is_empty_extraction_result(extraction_type: str, value: Any) -> bool:
        if extraction_type == "count":
            return isinstance(value, int) and value == 0
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, list):
            return len(value) == 0
        return False

    def download_file(self, url: str, timeout: Optional[int] = None) -> tuple[bytes, Dict[str, str]]:
        """Download raw bytes for a remote resource via Playwright."""
        with self._lock:
            self._ensure_browser()
            playwright = self._playwright
            assert playwright is not None
            request_context = playwright.request.new_context()
            try:
                response = request_context.get(url, timeout=timeout or config.PLAYWRIGHT_NAVIGATION_TIMEOUT_MS)
            except PlaywrightError:
                request_context.dispose()
                raise

            try:
                if not response.ok:
                    status = response.status
                    body_preview = response.text()[:200]
                    raise PlaywrightError(f"Request to {url} failed with status {status}: {body_preview}")

                data = response.body()
                headers = response.headers
                return data, headers
            finally:
                request_context.dispose()

    def _post_process_extractions(
        self,
        extracts: List[Dict[str, Any]],
        logs: List[str],
        page_url: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Convert large HTML payloads to Markdown, apply filters, and enforce length limits."""
        processed: List[Dict[str, Any]] = []
        converter = _get_html_converter()
        max_html = max(config.PLAYWRIGHT_MAX_HTML_CHARS, 0)
        max_markdown = max(config.PLAYWRIGHT_MAX_MARKDOWN_CHARS, 0)
        max_extraction_chars = max(config.PLAYWRIGHT_MAX_EXTRACTION_CHARS, 0)

        for idx, item in enumerate(extracts, start=1):
            entry = dict(item)
            extraction_type = entry.get("type")
            value = entry.get("value")
            metadata = dict(entry.pop("metadata", {}) or {})

            if isinstance(value, str) and extraction_type in {"html", "outer_html"}:
                raw_html_length = len(value)
                html_for_conversion = value
                html_truncated = False

                if max_html and raw_html_length > max_html:
                    html_for_conversion = value[:max_html]
                    html_truncated = True
                    logs.append(
                        f"Extraction {idx}: Raw HTML truncated from {raw_html_length} to {len(html_for_conversion)} characters before conversion."
                    )

                conversion_successful = False
                markdown_text = html_for_conversion
                markdown_truncated = False

                if converter is not None:
                    try:
                        markdown_result = converter.convert_string(html_for_conversion, url=page_url)
                        markdown_text = markdown_result.markdown.strip()
                        conversion_successful = True
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.warning("MarkItDown conversion failed", exc_info=exc)
                        logs.append(
                            f"Extraction {idx}: Markdown conversion failed ({exc.__class__.__name__}); returning truncated HTML."
                        )
                else:
                    logs.append(f"Extraction {idx}: MarkItDown not installed; returning truncated HTML.")

                if conversion_successful and max_markdown and len(markdown_text) > max_markdown:
                    markdown_text = markdown_text[:max_markdown] + "\n\n[...truncated...]"
                    markdown_truncated = True
                    logs.append(f"Extraction {idx}: Markdown truncated to {max_markdown} characters.")

                entry["value"] = markdown_text
                entry["value_format"] = "markdown" if conversion_successful else "html"
                metadata.update(
                    {
                        "raw_html_length": raw_html_length,
                        "markdown_length": len(markdown_text),
                        "raw_html_truncated": html_truncated,
                        "markdown_truncated": markdown_truncated,
                        "conversion": "markdown" if conversion_successful else "html",
                    }
                )

            keywords = entry.pop("keywords", None)
            page_range = entry.pop("page_range", None)
            filters_metadata: Dict[str, Any] = {}

            if keywords:
                filtered_value, keyword_meta = self._filter_by_keywords(entry.get("value"), keywords)
                filters_metadata["keywords"] = keyword_meta
                entry["value"] = filtered_value
                if keyword_meta.get("removed_all"):
                    logs.append(
                        f"Extraction {idx}: Keyword filter removed all content. Adjust keywords or refine the selector."
                    )

            if page_range:
                filtered_value, page_meta = self._filter_by_page_range(entry.get("value"), page_range)
                filters_metadata["page_range"] = page_meta
                entry["value"] = filtered_value
                if page_meta.get("removed_all"):
                    logs.append(
                        f"Extraction {idx}: Page range {page_meta.get('start')}-{page_meta.get('end')} removed all content."
                    )

            if filters_metadata:
                metadata.setdefault("filters", {}).update(filters_metadata)

            value_after_filters = entry.get("value")

            if max_extraction_chars and isinstance(value_after_filters, (str, list)):
                truncated_value, truncation_meta = self._truncate_value(value_after_filters, max_extraction_chars)
                entry["value"] = truncated_value
                metadata.setdefault("length", {})
                metadata["length"]["original"] = truncation_meta.get("original_length", 0)
                metadata["length"]["kept"] = truncation_meta.get("kept_length", 0)
                if truncation_meta.get("truncated"):
                    metadata["truncated"] = True
                    metadata["truncation_message"] = (
                        f"Trimmed to {max_extraction_chars} characters. Narrow selectors or add keywords/page_range."
                    )
                    logs.append(
                        f"Extraction {idx}: Value truncated from {truncation_meta.get('original_length', 0)} to "
                        f"{truncation_meta.get('kept_length', 0)} characters."
                    )
                else:
                    metadata.setdefault("truncated", False)
            elif metadata:
                metadata.setdefault("truncated", False)

            if metadata:
                entry["metadata"] = metadata

            processed.append(entry)

        return processed

    def _capture_screenshot_if_requested(
        self, page: Any, screenshot_option: Any, logs: List[str]
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Capture a screenshot when the caller opts in."""
        if not screenshot_option:
            return None, None

        full_page = False
        selector: Optional[str] = None

        if isinstance(screenshot_option, bool):
            full_page = screenshot_option
        elif isinstance(screenshot_option, dict):
            full_page = bool(screenshot_option.get("full_page", False))
            selector_value = screenshot_option.get("selector")
            if isinstance(selector_value, str) and selector_value.strip():
                selector = selector_value.strip()
        else:
            raise ValueError("Screenshot option must be a boolean or an object.")

        if selector:
            logs.append(f"Screenshot: capturing element {selector}")
            locator = page.locator(selector)
            png_bytes = locator.screenshot()
        else:
            logs.append(f"Screenshot: capturing page (full_page={full_page})")
            png_bytes = page.screenshot(full_page=full_page)

        metadata = {
            "bytes": len(png_bytes),
            "full_page": full_page,
        }
        if selector:
            metadata["selector"] = selector

        encoded_png = base64.b64encode(png_bytes).decode("utf-8")

        return metadata, encoded_png

    def _normalize_keywords(self, raw_keywords: Any) -> List[str]:
        if raw_keywords is None:
            return []
        if not isinstance(raw_keywords, list):
            raise ValueError("keywords must be an array of strings.")
        cleaned: List[str] = []
        for keyword in raw_keywords:
            if not isinstance(keyword, str):
                raise ValueError("keywords array must contain only strings.")
            stripped = keyword.strip()
            if stripped:
                cleaned.append(stripped)
        return cleaned

    def _normalize_page_range(self, raw_page_range: Any) -> Optional[Tuple[int, int]]:
        if raw_page_range in (None, "", []):
            return None

        def _validate_bounds(start: int, end: int) -> Tuple[int, int]:
            if start < 1 or end < 1:
                raise ValueError("page_range values must be positive integers.")
            if end < start:
                raise ValueError("page_range end must be greater than or equal to start.")
            return start, end

        if isinstance(raw_page_range, str):
            text = raw_page_range.strip()
            if not text:
                return None
            if "-" in text:
                start_text, end_text = text.split("-", 1)
                start = int(start_text.strip())
                end = int(end_text.strip())
            else:
                start = end = int(text)
            return _validate_bounds(start, end)

        if isinstance(raw_page_range, (list, tuple)):
            if len(raw_page_range) == 1:
                value = int(raw_page_range[0])
                return _validate_bounds(value, value)
            if len(raw_page_range) >= 2:
                start = int(raw_page_range[0])
                end = int(raw_page_range[1])
                return _validate_bounds(start, end)

        raise ValueError("page_range must be a string like '2-4' or an array [start, end].")

    def _filter_by_keywords(self, value: Any, keywords: List[str]) -> Tuple[Any, Dict[str, Any]]:
        meta: Dict[str, Any] = {
            "applied": False,
            "matched_segments": 0,
            "keyword_count": len(keywords),
            "removed_all": False,
        }
        if not keywords:
            return value, meta

        lowered_keywords = [kw.lower() for kw in keywords]
        meta["applied"] = True

        if isinstance(value, str):
            lines = value.splitlines()
            kept_lines = [line for line in lines if any(kw in line.lower() for kw in lowered_keywords)]
            meta["matched_segments"] = len(kept_lines)
            if kept_lines:
                return "\n".join(kept_lines), meta
            meta["removed_all"] = True
            return "", meta

        if isinstance(value, list):
            kept_items = []
            for item in value:
                text = str(item)
                if any(kw in text.lower() for kw in lowered_keywords):
                    kept_items.append(item)
            meta["matched_segments"] = len(kept_items)
            if kept_items:
                return kept_items, meta
            meta["removed_all"] = True
            return [], meta

        meta["applied"] = False
        meta["reason"] = "unsupported_type"
        return value, meta

    def _filter_by_page_range(self, value: Any, page_range: Tuple[int, int]) -> Tuple[Any, Dict[str, Any]]:
        start, end = page_range
        meta: Dict[str, Any] = {
            "applied": True,
            "start": start,
            "end": end,
            "total_segments": 0,
            "kept_segments": 0,
            "removed_all": False,
        }

        if isinstance(value, list):
            total = len(value)
            meta["total_segments"] = total
            if total == 0:
                return value, meta
            start_idx = max(start - 1, 0)
            end_idx = min(end, total)
            filtered = value[start_idx:end_idx]
            meta["kept_segments"] = len(filtered)
            if not filtered:
                meta["removed_all"] = True
            return filtered, meta

        if isinstance(value, str):
            if not value:
                return value, meta
            if "\n\n" in value:
                segments = value.split("\n\n")
                joiner = "\n\n"
            else:
                segments = value.splitlines()
                joiner = "\n"
            total = len(segments)
            meta["total_segments"] = total
            if total == 0:
                return value, meta
            start_idx = max(start - 1, 0)
            end_idx = min(end, total)
            filtered_segments = segments[start_idx:end_idx]
            meta["kept_segments"] = len(filtered_segments)
            if not filtered_segments:
                meta["removed_all"] = True
                return "", meta
            return joiner.join(filtered_segments), meta

        meta["applied"] = False
        meta["reason"] = "unsupported_type"
        return value, meta

    def _truncate_value(self, value: Any, limit: int) -> Tuple[Any, Dict[str, Any]]:
        meta: Dict[str, Any] = {
            "truncated": False,
            "original_length": 0,
            "kept_length": 0,
        }
        if limit <= 0:
            return value, meta

        if isinstance(value, str):
            original_length = len(value)
            meta["original_length"] = original_length
            if original_length <= limit:
                meta["kept_length"] = original_length
                return value, meta

            suffix = f"\n{TRUNCATION_SUFFIX}" if limit > len(TRUNCATION_SUFFIX) + 1 else ""
            available = max(limit - len(suffix), 0)
            truncated_text = value[:available].rstrip()
            if suffix:
                truncated_text = f"{truncated_text}{suffix}"
            else:
                truncated_text = value[:limit]
            meta["truncated"] = True
            meta["kept_length"] = len(truncated_text)
            return truncated_text, meta

        if isinstance(value, list):
            text_lengths = [len(str(item)) for item in value]
            original_length = sum(text_lengths)
            meta["original_length"] = original_length
            if original_length <= limit:
                meta["kept_length"] = original_length
                return value, meta

            remaining = limit
            truncated_items: List[Any] = []
            for item, item_length in zip(value, text_lengths, strict=False):
                if remaining <= 0:
                    break
                if item_length <= remaining:
                    truncated_items.append(item)
                    remaining -= item_length
                    continue
                slice_length = max(remaining - len(TRUNCATION_SUFFIX), 0)
                truncated_item = str(item)[:slice_length].rstrip()
                if slice_length > 0:
                    truncated_item = f"{truncated_item}{TRUNCATION_SUFFIX}"
                else:
                    truncated_item = TRUNCATION_SUFFIX
                truncated_items.append(truncated_item)
                remaining = 0
                break

            meta["truncated"] = True
            meta["kept_length"] = sum(len(str(item)) for item in truncated_items)
            return truncated_items, meta

        return value, meta

    def _require_selector(self, payload: Dict[str, Any], context: str) -> str:
        selector = payload.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError(f"{context} requires a non-empty 'selector'.")
        return selector.strip()

    def _error(self, code: str, message: str, logs: List[str]) -> Dict[str, Any]:
        logs.append(f"Error: {message}")
        return {"success": False, "error": code, "detail": message, "logs": logs}


playwright_manager = PlaywrightManager()
