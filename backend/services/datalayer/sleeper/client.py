"""One-attempt Sleeper HTTP client with complete, sanitized outcomes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import hashlib
import math
from time import perf_counter
from typing import Protocol
from urllib.parse import urlsplit

import requests

from backend.services.datalayer.canonical_json import (
    canonical_json_bytes,
    parse_json_bytes,
)
from backend.services.datalayer.contracts import RequestStatus
from backend.services.datalayer.sleeper.responses import (
    EndpointRequest,
    FailedSourceAttempt,
    RequestParameter,
    SanitizedSourceError,
    SourceAttempt,
    SuccessfulSourceAttempt,
)


WallClock = Callable[[], datetime]
MonotonicClock = Callable[[], float]


class HttpResponse(Protocol):
    status_code: int

    @property
    def content(self) -> bytes: ...


class SleeperTransport(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, RequestParameter],
        headers: Mapping[str, str],
        timeout: float,
        allow_redirects: bool,
    ) -> HttpResponse: ...


class SleeperSourceClient:
    """Execute exactly one request; callers own retry and persistence policy."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.sleeper.app/v1",
        timeout_seconds: float = 10,
        transport: SleeperTransport | None = None,
        clock: WallClock | None = None,
        monotonic_clock: MonotonicClock | None = None,
    ) -> None:
        self._base_url = _validated_base_url(base_url)
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("Sleeper timeout must be positive")
        self._timeout_seconds = timeout_seconds
        self._transport = transport if transport is not None else requests.Session()
        self._owns_transport = transport is None
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic_clock = monotonic_clock or perf_counter

    def execute(self, request: EndpointRequest) -> SourceAttempt:
        requested_at = self._clock()
        started = self._monotonic_clock()
        try:
            response = self._transport.get(
                f"{self._base_url}{request.path}",
                params=request.parameters,
                headers={"User-Agent": "aidam-datalayer"},
                timeout=self._timeout_seconds,
                allow_redirects=False,
            )
        except requests.RequestException:
            return self._failed_attempt(
                request,
                requested_at=requested_at,
                started=started,
                status=RequestStatus.TRANSPORT_ERROR,
                http_status=None,
                code="sleeper_transport_error",
                summary="Sleeper could not be reached",
            )

        if response.status_code < 200 or response.status_code >= 300:
            return self._failed_attempt(
                request,
                requested_at=requested_at,
                started=started,
                status=RequestStatus.HTTP_ERROR,
                http_status=response.status_code,
                code="sleeper_http_error",
                summary=f"Sleeper returned HTTP {response.status_code}",
            )

        try:
            payload = parse_json_bytes(response.content)
            canonical = canonical_json_bytes(payload)
        except (TypeError, ValueError):
            return self._failed_attempt(
                request,
                requested_at=requested_at,
                started=started,
                status=RequestStatus.INVALID_PAYLOAD,
                http_status=response.status_code,
                code="sleeper_invalid_json",
                summary="Sleeper returned an invalid JSON payload",
            )

        return SuccessfulSourceAttempt(
            endpoint=request,
            requested_at=requested_at,
            completed_at=self._clock(),
            http_status=response.status_code,
            latency_ms=self._elapsed_ms(started),
            payload=payload,
            raw_sha256=hashlib.sha256(canonical).hexdigest(),
            byte_length=len(canonical),
            media_type="application/json",
        )

    def close(self) -> None:
        if self._owns_transport:
            self._transport.close()  # type: ignore[attr-defined]

    def _failed_attempt(
        self,
        endpoint: EndpointRequest,
        *,
        requested_at: datetime,
        started: float,
        status: RequestStatus,
        http_status: int | None,
        code: str,
        summary: str,
    ) -> FailedSourceAttempt:
        return FailedSourceAttempt(
            endpoint=endpoint,
            requested_at=requested_at,
            completed_at=self._clock(),
            status=status,
            http_status=http_status,
            latency_ms=self._elapsed_ms(started),
            error=SanitizedSourceError(code=code, summary=summary),
        )

    def _elapsed_ms(self, started: float) -> int:
        return max(0, round((self._monotonic_clock() - started) * 1000))


def _validated_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        any(character.isspace() for character in normalized)
        or parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Sleeper base URL must be an HTTP(S) URL without credentials")
    return normalized
