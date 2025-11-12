"""Caching layer for HTTP responses."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from typing import Optional

from .utils import logger


SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class SQLiteCache:
    """SQLite-backed cache with very small footprint."""

    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(SCHEMA)
            conn.commit()

    def get(self, key: str) -> Optional[str]:
        with closing(sqlite3.connect(self.path)) as conn:
            cur = conn.execute("SELECT value FROM http_cache WHERE key = ?", (key,))
            row = cur.fetchone()
            if row:
                return row[0]
        return None

    def set(self, key: str, value: str) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO http_cache(key, value) VALUES(?, ?)",
                (key, value),
            )
            conn.commit()


class CacheManager:
    """Facade for caches that allows injection in tests."""

    def __init__(self, cache_dir: str | None = None) -> None:
        self.cache_dir = cache_dir or os.path.join(os.getcwd(), ".wikinet-cache")
        self.sqlite_cache = SQLiteCache(os.path.join(self.cache_dir, "http_cache.sqlite"))

    def get(self, key: str) -> Optional[str]:
        return self.sqlite_cache.get(key)

    def set(self, key: str, value: str) -> None:
        self.sqlite_cache.set(key, value)


__all__ = ["CacheManager", "SQLiteCache"]
