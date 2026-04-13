"""
Thread-safe in-memory store for recent test execution reports (GET /test-history).

For production at scale, swap this for Redis or a database using the same interface.
"""
from __future__ import annotations

from threading import Lock
from typing import Any

from app.config import settings


class TestHistoryStore:
    def __init__(self, max_entries: int) -> None:
        self._max = max(1, max_entries)
        self._items: list[dict[str, Any]] = []
        self._lock = Lock()

    def append(self, report: dict[str, Any]) -> None:
        with self._lock:
            self._items.insert(0, report)
            del self._items[self._max :]

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            n = max(1, min(limit, 500))
            return list(self._items[:n])


_store: TestHistoryStore | None = None


def get_test_history_store() -> TestHistoryStore:
    global _store
    if _store is None:
        _store = TestHistoryStore(settings.test_history_max_entries)
    return _store
