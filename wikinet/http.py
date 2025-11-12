"""HTTP client with caching, retries, and throttling."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Mapping, Optional

import requests

from .cache import CacheManager
from .utils import RateLimiter, hash_request, logger, merge_dicts

DEFAULT_HEADERS = {
    "User-Agent": os.getenv("WIKINET_USER_AGENT", "wikinet/1.0 (+https://example.com/contact)"),
}


class HTTPError(RuntimeError):
    pass


class HTTPClient:
    def __init__(
        self,
        cache: CacheManager | None = None,
        rate_limiter: RateLimiter | None = None,
        max_retries: int = 3,
        backoff: float = 0.5,
        timeout: int = 30,
    ) -> None:
        self.cache = cache
        self.rate_limiter = rate_limiter or RateLimiter()
        self.max_retries = max_retries
        self.backoff = backoff
        self.timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        json_body: Optional[Any] = None,
        use_cache: bool = True,
    ) -> requests.Response:
        headers = merge_dicts(DEFAULT_HEADERS, dict(headers or {}))
        cache_key = hash_request(method, url, params, json_body)
        if method.upper() == "GET" and use_cache and self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                response = requests.Response()
                response.status_code = 200
                response._content = cached.encode("utf-8")  # type: ignore[attr-defined]
                response.headers = requests.structures.CaseInsensitiveDict()
                response.headers["X-Wikinet-Cache"] = "HIT"
                response.url = url
                return response

        for attempt in range(self.max_retries):
            self.rate_limiter.wait()
            resp = requests.request(
                method,
                url,
                params=params,
                headers=headers,
                json=json_body,
                timeout=self.timeout,
            )
            if resp.status_code in (200, 304):
                if method.upper() == "GET" and use_cache and self.cache:
                    self.cache.set(cache_key, resp.text)
                return resp
            if resp.status_code in {429, 500, 502, 503, 504}:
                sleep_for = self.backoff * (2**attempt)
                logger.warning("HTTP %s returned %s, retrying in %.2fs", url, resp.status_code, sleep_for)
                time.sleep(sleep_for)
                continue
            raise HTTPError(f"Request failed with status {resp.status_code}: {resp.text[:200]}")
        raise HTTPError(f"Exceeded retries for {url}")

    def get_json(
        self,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        resp = self.request("GET", url, params=params, headers=headers, use_cache=use_cache)
        try:
            return resp.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise HTTPError(f"Invalid JSON response from {url}") from exc


__all__ = ["HTTPClient", "HTTPError", "DEFAULT_HEADERS"]
