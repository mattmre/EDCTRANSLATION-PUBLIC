"""Small JSON HTTP helper used by optional live provider adapters."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class JsonHttpError(RuntimeError):
    """Raised for HTTP transport failures without exposing secret values."""


class JsonHttpClient:
    def __init__(self, *, timeout_seconds: float = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def get_json(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request = Request(url, headers=headers or {}, method="GET")
        return self._send(request)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request_headers = {"content-type": "application/json"}
        request_headers.update(headers or {})
        request = Request(url, data=body, headers=request_headers, method="POST")
        return self._send(request)

    def _send(self, request: Request) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise JsonHttpError(f"HTTP {exc.code} from provider endpoint") from exc
        except URLError as exc:
            raise JsonHttpError("provider endpoint is unreachable") from exc
        except TimeoutError as exc:
            raise JsonHttpError("provider endpoint timed out") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JsonHttpError("provider endpoint returned non-JSON response") from exc
        if not isinstance(payload, dict):
            raise JsonHttpError("provider endpoint returned non-object JSON")
        return payload
