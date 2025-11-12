"""Minimal requests-compatible client for offline environments."""

from __future__ import annotations

import importlib.util
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping, Optional

_spec = importlib.util.find_spec("requests")
if _spec and _spec.origin and os.path.abspath(_spec.origin) != os.path.abspath(__file__):  # pragma: no cover
    module = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(module)
    locals().update(module.__dict__)
else:  # pragma: no cover - lightweight fallback
    class CaseInsensitiveDict(dict):
        def __init__(self, *args, **kwargs):
            super().__init__()
            self.update(*args, **kwargs)

        def __getitem__(self, key):
            return super().__getitem__(key.lower())

        def __setitem__(self, key, value):
            super().__setitem__(key.lower(), value)

        def __contains__(self, key):
            return super().__contains__(key.lower())

        def update(self, *args, **kwargs):
            for k, v in dict(*args, **kwargs).items():
                super().__setitem__(k.lower(), v)

    class Response:
        def __init__(self) -> None:
            self.status_code = 0
            self._content = b""
            self.headers: CaseInsensitiveDict = CaseInsensitiveDict()
            self.url = ""

        @property
        def text(self) -> str:
            return self._content.decode("utf-8", errors="replace")

        def json(self) -> Any:
            return json.loads(self.text)

        def raise_for_status(self) -> None:
            if not (200 <= self.status_code < 400):
                raise HTTPError(f"HTTP {self.status_code}: {self.text[:200]}")

    class HTTPError(Exception):
        pass

    class Timeout(Exception):  # pragma: no cover
        pass

    class exceptions:  # pragma: no cover
        RequestException = HTTPError

    class structures:  # pragma: no cover
        CaseInsensitiveDict = CaseInsensitiveDict

    def _encode_params(params: Optional[Mapping[str, Any]]) -> str:
        if not params:
            return ""
        return urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})

    def request(
        method: str,
        url: str,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        json: Any = None,
        timeout: Optional[int] = None,
    ) -> Response:
        method = method.upper()
        headers = headers or {}
        data = None
        if params:
            query = _encode_params(params)
            separator = '&' if urllib.parse.urlparse(url).query else '?'
            url = f"{url}{separator}{query}"
        if json is not None:
            data = json.dumps(json).encode("utf-8")
            headers = {**headers, "Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=dict(headers), method=method)
        resp = Response()
        resp.url = url
        try:
            with urllib.request.urlopen(req, timeout=timeout) as fh:
                resp.status_code = fh.getcode() or 0
                resp._content = fh.read()
                resp.headers.update(dict(fh.headers))
        except urllib.error.HTTPError as exc:  # pragma: no cover
            resp.status_code = exc.code
            resp._content = exc.read()
            resp.headers.update(dict(exc.headers or {}))
        except urllib.error.URLError as exc:  # pragma: no cover
            raise HTTPError(str(exc)) from exc
        return resp

    __all__ = [
        "request",
        "Response",
        "HTTPError",
        "Timeout",
        "exceptions",
        "structures",
    ]
