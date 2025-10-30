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
from typing import Any, Dict, List, Optional

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

            if extraction_type == "evaluate":
                expression = extraction.get("expression")
                if not isinstance(expression, str) or not expression.strip():
                    raise ValueError(f"Extraction {idx} (evaluate) requires 'expression'.")
                logs.append(f"Extraction {idx}: evaluate JavaScript expression")
                value = page.evaluate(expression)
                entry["value"] = _json_safe(value)
            else:
                selector = self._require_selector(extraction, context=f"extraction {idx}")
                entry["selector"] = selector
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

            results.append(entry)

        return results

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
        """Convert large HTML payloads to Markdown and enforce length limits."""
        processed: List[Dict[str, Any]] = []
        converter = _get_html_converter()
        max_html = max(config.PLAYWRIGHT_MAX_HTML_CHARS, 0)
        max_markdown = max(config.PLAYWRIGHT_MAX_MARKDOWN_CHARS, 0)

        for idx, item in enumerate(extracts, start=1):
            entry = dict(item)
            extraction_type = entry.get("type")
            value = entry.get("value")

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
                entry["metadata"] = {
                    "raw_html_length": raw_html_length,
                    "markdown_length": len(markdown_text),
                    "raw_html_truncated": html_truncated,
                    "markdown_truncated": markdown_truncated,
                    "conversion": "markdown" if conversion_successful else "html",
                }

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

    def _require_selector(self, payload: Dict[str, Any], context: str) -> str:
        selector = payload.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError(f"{context} requires a non-empty 'selector'.")
        return selector.strip()

    def _error(self, code: str, message: str, logs: List[str]) -> Dict[str, Any]:
        logs.append(f"Error: {message}")
        return {"success": False, "error": code, "detail": message, "logs": logs}


playwright_manager = PlaywrightManager()
