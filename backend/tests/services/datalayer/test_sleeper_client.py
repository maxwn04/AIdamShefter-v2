from datetime import datetime, timezone
import json
from typing import Any

import requests

from backend.services.datalayer.canonical_json import canonical_json_bytes
from backend.services.datalayer.sleeper.client import SleeperSourceClient
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


class StubResponse:
    def __init__(self, status_code: int, payload: Any = None, error: ValueError | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self._error = error

    @property
    def content(self) -> bytes:
        if self._error is not None:
            raise self._error
        return json.dumps(self._payload, separators=(",", ":")).encode()


class StubSession:
    def __init__(self, result: StubResponse | requests.RequestException) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> StubResponse:
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.result, requests.RequestException):
            raise self.result
        return self.result


def endpoint_request() -> EndpointRequest:
    return EndpointRequest(
        endpoint_kind=EndpointKind.MATCHUPS,
        scope_key=ScopeKey.from_parts(EndpointKind.MATCHUPS, "season", 8),
        path="/league/123/matchups/8",
        week=8,
    )


def fixed_clock() -> datetime:
    return datetime(2025, 10, 28, tzinfo=timezone.utc)


def test_successful_attempt_captures_canonical_payload_receipt() -> None:
    session = StubSession(StubResponse(200, {"b": 2, "a": 1}))
    client = SleeperSourceClient(session=session, clock=fixed_clock)  # type: ignore[arg-type]

    result = client.execute(endpoint_request())

    assert result.outcome == "succeeded"
    assert result.byte_length == len(canonical_json_bytes({"a": 1, "b": 2}))
    assert session.calls[0]["url"].endswith("/league/123/matchups/8")


def test_transport_error_is_a_sanitized_failed_attempt() -> None:
    session = StubSession(requests.ConnectionError("secret host detail"))
    client = SleeperSourceClient(session=session, clock=fixed_clock)  # type: ignore[arg-type]

    result = client.execute(endpoint_request())

    assert result.outcome == "failed"
    assert result.status == "transport_error"
    assert "secret host detail" not in result.error.summary


def test_http_and_invalid_json_are_recordable_failures() -> None:
    http_client = SleeperSourceClient(
        session=StubSession(StubResponse(503)),  # type: ignore[arg-type]
        clock=fixed_clock,
    )
    json_client = SleeperSourceClient(
        session=StubSession(StubResponse(200, error=ValueError("bad body"))),  # type: ignore[arg-type]
        clock=fixed_clock,
    )

    http_result = http_client.execute(endpoint_request())
    json_result = json_client.execute(endpoint_request())

    assert http_result.outcome == "failed"
    assert http_result.status == "http_error"
    assert json_result.outcome == "failed"
    assert json_result.status == "invalid_payload"
