"""Sleeper API client with minimal GET support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


class SleeperApiError(RuntimeError):
    """Raised for Sleeper API request failures."""


@dataclass(frozen=True)
class SleeperClient:
    base_url: str = "https://api.sleeper.app/v1/"
    timeout_seconds: int = 10

    def get_json(
        self, path: str, params: Optional[Mapping[str, Any]] = None
    ) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        if params:
            url = f"{url}?{urlencode(params)}"

        req = Request(url, headers={"User-Agent": "sleeper-data-layer"})
        try:
            with urlopen(req, timeout=self.timeout_seconds) as resp:
                status = getattr(resp, "status", resp.getcode())
                body = resp.read().decode("utf-8")
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8") if exc.fp else ""
            raise SleeperApiError(
                f"HTTP {exc.code} for {url}: {error_body or exc.reason}"
            ) from exc
        except URLError as exc:
            raise SleeperApiError(f"Request failed for {url}: {exc.reason}") from exc

        if status and status >= 400:
            raise SleeperApiError(f"HTTP {status} for {url}: {body}")

        if not body:
            raise SleeperApiError(f"Empty response for {url}")

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise SleeperApiError(f"Invalid JSON from {url}") from exc
