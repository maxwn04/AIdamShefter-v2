"""Sleeper API client with minimal GET support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import requests


class SleeperApiError(RuntimeError):
    """Raised for Sleeper API request failures."""


@dataclass(frozen=True)
class SleeperClient:
    base_url: str = "https://api.sleeper.app/v1/"
    timeout_seconds: int = 10

    def get_json(
        self, path: str, params: Optional[Mapping[str, Any]] = None
    ) -> Any:
        try:
            response = requests.get(
                f"{self.base_url.rstrip('/')}/{path.lstrip('/')}",
                params=params,
                headers={"User-Agent": "sleeper-data-layer"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            error_body = exc.response.text if exc.response is not None else ""
            raise SleeperApiError(
                f"HTTP {exc.response.status_code} for {response.url}: "
                f"{error_body or exc}"
            ) from exc
        except requests.RequestException as exc:
            raise SleeperApiError(f"Request failed for {self.base_url}: {exc}") from exc

        if not response.text:
            raise SleeperApiError(f"Empty response for {response.url}")

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise SleeperApiError(f"Invalid JSON from {response.url}") from exc
