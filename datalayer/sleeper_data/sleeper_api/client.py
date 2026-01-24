"""Sleeper API client with minimal GET support and local caching."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
        cache_path = _cache_path(self.base_url, path, params)
        cached_payload = _read_cached_payload(cache_path)
        if cached_payload is not None:
            return cached_payload

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
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise SleeperApiError(f"Invalid JSON from {response.url}") from exc

        _write_cached_payload(cache_path, payload)
        return payload


_CACHE_DIR = Path(".cache") / "sleeper"
_CACHE_TTL = timedelta(days=1)


def _cache_key(base_url: str, path: str, params: Optional[Mapping[str, Any]]) -> str:
    normalized = {
        "base_url": base_url.rstrip("/"),
        "path": f"/{path.lstrip('/')}",
        "params": params or {},
    }
    key_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(key_json.encode("utf-8")).hexdigest()


def _cache_path(
    base_url: str, path: str, params: Optional[Mapping[str, Any]]
) -> Path:
    return _CACHE_DIR / f"{_cache_key(base_url, path, params)}.json"


def _read_cached_payload(cache_path: Path) -> Optional[Any]:
    if not cache_path.exists():
        return None

    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    fetched_at = cached.get("fetched_at")
    if not fetched_at:
        return None

    try:
        fetched_dt = datetime.fromisoformat(fetched_at)
    except ValueError:
        return None

    if fetched_dt.tzinfo is None:
        fetched_dt = fetched_dt.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) - fetched_dt >= _CACHE_TTL:
        return None

    return cached.get("payload")


def _write_cached_payload(cache_path: Path, payload: Any) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "payload": payload,
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    except OSError:
        return
