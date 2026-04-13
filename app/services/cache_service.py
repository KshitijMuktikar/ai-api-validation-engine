"""
In-memory TTL cache for validation results.

Keyed by a hash of schema + response + routing fields to avoid duplicate LLM work.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Optional

from app.config import settings
from app.logging_config import get_logger
from app.models.schemas import ValidationResult

logger = get_logger(__name__)


@dataclass
class _CacheEntry:
    result: ValidationResult
    expires_at: float


class ValidationCache:
    """Simple thread-safe TTL map with a maximum size (evict oldest)."""

    def __init__(self, ttl_seconds: int, max_entries: int) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._data: dict[str, _CacheEntry] = {}
        self._lock = Lock()

    def _evict_if_needed(self) -> None:
        if len(self._data) <= self._max:
            return
        # Remove expired first
        now = time.monotonic()
        dead = [k for k, e in self._data.items() if e.expires_at <= now]
        for k in dead:
            del self._data[k]
        # Then oldest by insertion order (Python 3.7+ dict preserves order)
        while len(self._data) > self._max:
            first = next(iter(self._data))
            del self._data[first]

    @staticmethod
    def make_key(
        schema: dict[str, Any],
        response_body: Any,
        path: str,
        method: str,
        status_code: str,
        use_llm_semantic: bool,
        include_schema_in_prompt: bool,
        skip_llm_on_structural_failure: bool = False,
    ) -> str:
        """Stable hash for cache lookup."""
        payload = {
            "schema": schema,
            "body": response_body,
            "path": path,
            "method": method.lower(),
            "status": str(status_code),
            "llm": use_llm_semantic,
            "inc_schema": include_schema_in_prompt,
            "skip_llm_struct": skip_llm_on_structural_failure,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get(self, key: str) -> Optional[ValidationResult]:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                del self._data[key]
                return None
            # Refresh LRU-ish: move to end
            val = entry.result
            del self._data[key]
            self._data[key] = _CacheEntry(result=val, expires_at=entry.expires_at)
            return val.model_copy(update={"cached": True})

    def set(self, key: str, result: ValidationResult) -> None:
        with self._lock:
            self._data[key] = _CacheEntry(
                result=result.model_copy(update={"cached": False}),
                expires_at=time.monotonic() + self._ttl,
            )
            self._evict_if_needed()


_cache: Optional[ValidationCache] = None


def get_validation_cache() -> ValidationCache:
    global _cache
    if _cache is None:
        _cache = ValidationCache(
            ttl_seconds=max(0, settings.validation_cache_ttl_seconds),
            max_entries=max(1, settings.validation_cache_max_entries),
        )
    return _cache
