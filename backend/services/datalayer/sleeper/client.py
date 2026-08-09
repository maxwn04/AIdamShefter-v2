"""One-attempt Sleeper HTTP client with complete, sanitized outcomes."""

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
from time import perf_counter

import requests

from backend.json import canonical_json_bytes, parse_json_bytes
from .responses import (
    EndpointRequest,
    FailedSourceAttempt,
    SanitizedSourceError,
    SourceAttempt,
    SuccessfulSourceAttempt,
)

Clock = Callable[[], datetime]


class SleeperSourceClient:
    """Execute exactly one HTTP attempt; orchestration owns retries and audit."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.sleeper.app/v1",
        timeout_seconds: float = 10,
        session: requests.Session | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, request: EndpointRequest) -> SourceAttempt:
        requested_at = self._clock()
        started = perf_counter()
        try:
            response = self._session.get(
                f"{self._base_url}{request.path}",
                params=request.parameters,
                headers={"User-Agent": "aidam-datalayer"},
                timeout=self._timeout_seconds,
            )
        except requests.RequestException:
            return FailedSourceAttempt(
                endpoint=request,
                requested_at=requested_at,
                completed_at=self._clock(),
                status="transport_error",
                http_status=None,
                latency_ms=_elapsed_ms(started),
                error=SanitizedSourceError(
                    code="sleeper_transport_error",
                    summary="Sleeper could not be reached",
                ),
            )

        completed_at = self._clock()
        latency_ms = _elapsed_ms(started)
        if response.status_code < 200 or response.status_code >= 300:
            return FailedSourceAttempt(
                endpoint=request,
                requested_at=requested_at,
                completed_at=completed_at,
                status="http_error",
                http_status=response.status_code,
                latency_ms=latency_ms,
                error=SanitizedSourceError(
                    code="sleeper_http_error",
                    summary=f"Sleeper returned HTTP {response.status_code}",
                ),
            )

        try:
            payload = parse_json_bytes(response.content)
            canonical = canonical_json_bytes(payload)
        except (TypeError, ValueError):
            return FailedSourceAttempt(
                endpoint=request,
                requested_at=requested_at,
                completed_at=completed_at,
                status="invalid_payload",
                http_status=response.status_code,
                latency_ms=latency_ms,
                error=SanitizedSourceError(
                    code="sleeper_invalid_json",
                    summary="Sleeper returned an invalid JSON payload",
                ),
            )

        return SuccessfulSourceAttempt(
            endpoint=request,
            requested_at=requested_at,
            completed_at=completed_at,
            http_status=response.status_code,
            latency_ms=latency_ms,
            payload=payload,
            response_sha256=hashlib.sha256(canonical).hexdigest(),
            byte_length=len(canonical),
            media_type="application/json",
        )

    def close(self) -> None:
        if self._owns_session:
            self._session.close()
def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
