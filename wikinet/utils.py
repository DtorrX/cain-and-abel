"""Utility helpers for wikinet."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Optional

try:  # pragma: no cover - prefer rich when available
    from rich.console import Console
    from rich.logging import RichHandler
except Exception:  # pragma: no cover - fallback to stdlib
    class Console:  # type: ignore
        def log(self, *args, **kwargs):
            print(*args)

    class RichHandler(logging.StreamHandler):  # type: ignore
        def __init__(self, *args, **kwargs):
            super().__init__()

LOGGER_NAME = "wikinet"


def get_logger() -> logging.Logger:
    """Return a module-level logger configured with rich if not already."""
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = RichHandler(rich_tracebacks=True, show_path=False)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
    return logger


logger = get_logger()


def set_log_level(level: str) -> None:
    """Allow callers (e.g. CLI) to adjust logging verbosity at runtime."""

    level_value = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(level_value)


def hash_request(method: str, url: str, params: Optional[Mapping[str, Any]] = None, data: Optional[Any] = None) -> str:
    """Create a stable hash for caching HTTP requests."""
    payload = {
        "method": method.upper(),
        "url": url,
        "params": params or {},
        "data": data or {},
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


@dataclass
class RateLimiter:
    """Simple token bucket rate limiter."""

    rate: float = 5.0
    capacity: int = 5

    def __post_init__(self) -> None:  # pragma: no cover - trivial
        self._lock = threading.Lock()
        self._tokens = float(self.capacity)
        self._timestamp = time.perf_counter()

    def wait(self) -> None:
        with self._lock:
            now = time.perf_counter()
            elapsed = now - self._timestamp
            self._timestamp = now
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            if self._tokens < 1:
                sleep_for = (1 - self._tokens) / self.rate
                time.sleep(max(0, sleep_for))
                self._tokens = 0
                self._timestamp = time.perf_counter()
            self._tokens -= 1


console = Console()


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class MemoryCache(MutableMapping[str, str]):
    """In-memory cache useful for testing."""

    def __init__(self) -> None:
        self._store: Dict[str, str] = {}

    def __getitem__(self, key: str) -> str:
        return self._store[key]

    def __setitem__(self, key: str, value: str) -> None:
        self._store[key] = value

    def __delitem__(self, key: str) -> None:
        del self._store[key]

    def __iter__(self):  # pragma: no cover - trivial iterator
        return iter(self._store)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._store)


def merge_dicts(base: Dict[str, Any], override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    result = base.copy()
    if override:
        result.update({k: v for k, v in override.items() if v is not None})
    return result
