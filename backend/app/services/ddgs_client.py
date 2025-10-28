"""DDGS client wrapper with caching and logging support."""

from __future__ import annotations

import copy
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, Tuple

from ddgs import DDGS
from ddgs.exceptions import DDGSException, TimeoutException

from app.config import config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    """Structured DDGS search result container."""

    items: List[Dict[str, Any]]
    duration_ms: int
    cache_hit: bool
    backend: str
    backend_list: Tuple[str, ...]
    region: str
    safesearch: str
    timelimit: str | None
    max_results: int | None


class DDGSSearchError(Exception):
    """Normalize DDGS errors for the tool layer."""

    def __init__(self, code: str, message: str) -> None:
        """Store machine-readable code alongside the human-readable message."""
        super().__init__(message)
        self.code = code
        self.message = message


class DDGSClient:
    """Lightweight client around DDGS with TTL caching."""

    def __init__(self) -> None:
        """Initialise DDGS client with configured threads, cache, and proxy settings."""
        max_threads = config.DDGS_MAX_THREADS
        if max_threads is not None and max_threads > 0:
            DDGS.threads = max_threads

        self._ddgs = DDGS(proxy=config.DDGS_PROXY, timeout=config.DDGS_TIMEOUT, verify=config.DDGS_VERIFY_SSL)
        self._cache: "OrderedDict[str, Tuple[float, SearchResult]]" = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_ttl = max(0, config.DDGS_CACHE_TTL_SECONDS)
        self._cache_maxsize = max(0, config.DDGS_CACHE_MAXSIZE)

    @staticmethod
    def _normalize_backend_list(backend: str) -> Tuple[str, ...]:
        items = [b.strip() for b in backend.split(",") if b and b.strip()]
        return tuple(items) if items else ("auto",)

    @staticmethod
    def _make_cache_key(
        query: str,
        category: str,
        backend: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        max_results: int | None,
        extra: Dict[str, Any] | None = None,
    ) -> str:
        extra_items: Iterable[Tuple[str, Any]] = sorted((extra or {}).items())
        key_tuple = (
            query,
            category,
            backend,
            region,
            safesearch,
            timelimit or "",
            max_results or 0,
            tuple(extra_items),
        )
        return repr(key_tuple)

    def _get_cached(self, key: str) -> SearchResult | None:
        if self._cache_ttl == 0 or self._cache_maxsize == 0:
            return None

        with self._cache_lock:
            cached = self._cache.get(key)
            if not cached:
                return None
            inserted_at, result = cached
            if time.time() - inserted_at > self._cache_ttl:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            first_item = result.items[0] if result.items else {}
            logger.info(
                "DDGS cache hit",
                extra={
                    "ddgs_query": first_item.get("_query", ""),
                    "ddgs_backend": result.backend,
                    "ddgs_category": first_item.get("_category", ""),
                },
            )
            return replace(result, cache_hit=True, items=copy.deepcopy(result.items))

    def _set_cache(self, key: str, result: SearchResult) -> None:
        if self._cache_ttl == 0 or self._cache_maxsize == 0:
            return

        with self._cache_lock:
            self._cache[key] = (time.time(), replace(result, items=copy.deepcopy(result.items)))
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_maxsize:
                self._cache.popitem(last=False)

    def search(
        self,
        *,
        query: str,
        category: str,
        backend: str,
        region: str,
        safesearch: str,
        timelimit: str | None,
        max_results: int | None,
        extra: Dict[str, Any] | None = None,
    ) -> SearchResult:
        """Execute a DDGS query, applying caching and converting to structured results."""
        cache_key = self._make_cache_key(query, category, backend, region, safesearch, timelimit, max_results, extra)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        ddgs_method_name = {
            "text": "text",
            "images": "images",
            "news": "news",
            "videos": "videos",
            "books": "books",
        }.get(category)
        if not ddgs_method_name:
            raise DDGSSearchError("unsupported_category", f"Unsupported DDGS category: {category}")

        ddgs_method = getattr(self._ddgs, ddgs_method_name)
        backend_list = self._normalize_backend_list(backend)

        start = time.perf_counter()

        try:
            items = ddgs_method(
                query,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
                max_results=max_results,
                backend=backend,
                **(extra or {}),
            )
        except TimeoutException as exc:  # pragma: no cover - network dependent
            raise DDGSSearchError("timeout", str(exc)) from exc
        except DDGSException as exc:  # pragma: no cover - library error
            raise DDGSSearchError("ddgs_error", str(exc)) from exc
        except Exception as exc:  # pragma: no cover - unexpected error
            raise DDGSSearchError("unexpected_error", str(exc)) from exc

        duration_ms = int((time.perf_counter() - start) * 1000)

        if not isinstance(items, list):
            items = []

        # Annotate each raw item with context for downstream consumers.
        annotated_items: List[Dict[str, Any]] = []
        for idx, item in enumerate(items, start=1):
            annotated = dict(item)
            annotated.setdefault("_rank", idx)
            annotated.setdefault("_backend", backend)
            annotated.setdefault("_category", category)
            annotated.setdefault("_region", region)
            annotated.setdefault("_query", query)
            annotated_items.append(annotated)

        result = SearchResult(
            items=annotated_items,
            duration_ms=duration_ms,
            cache_hit=False,
            backend=backend,
            backend_list=backend_list,
            region=region,
            safesearch=safesearch,
            timelimit=timelimit,
            max_results=max_results,
        )

        self._set_cache(cache_key, result)

        logger.info(
            "DDGS search completed",
            extra={
                "ddgs_query": query,
                "ddgs_category": category,
                "ddgs_backend": backend,
                "ddgs_region": region,
                "ddgs_result_count": len(items),
                "ddgs_duration_ms": duration_ms,
            },
        )

        return replace(result, items=copy.deepcopy(result.items))


_client_singleton: DDGSClient | None = None
_singleton_lock = threading.Lock()


def get_ddgs_client() -> DDGSClient:
    """Return the shared DDGS client instance."""
    global _client_singleton
    if _client_singleton is None:
        with _singleton_lock:
            if _client_singleton is None:
                _client_singleton = DDGSClient()
    return _client_singleton
