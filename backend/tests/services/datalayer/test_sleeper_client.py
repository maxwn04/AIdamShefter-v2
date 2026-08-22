from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import requests

from backend.services.datalayer.canonical_json import canonical_json_bytes
from backend.services.datalayer.contracts import RequestStatus
from backend.services.datalayer.local_files import (
    LocalArtifactKind,
    LocalDatalayerFileStore,
)
from backend.services.datalayer.sleeper.client import SleeperSourceClient
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


SEASON_ID = UUID("10000000-0000-0000-0000-000000000001")
REQUESTED_AT = datetime(2025, 10, 28, 12, tzinfo=timezone.utc)
COMPLETED_AT = REQUESTED_AT + timedelta(milliseconds=25)


class StubResponse:
    def __init__(self, status_code: int, content: bytes) -> None:
        self.status_code = status_code
        self._content = content
        self.content_reads = 0

    @property
    def content(self) -> bytes:
        self.content_reads += 1
        return self._content


class StubTransport:
    def __init__(
        self,
        result: StubResponse | requests.RequestException,
    ) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> StubResponse:
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.result, requests.RequestException):
            raise self.result
        return self.result

    def close(self) -> None:
        self.closed = True


def _endpoint() -> EndpointRequest:
    return EndpointRequest(
        endpoint_kind=EndpointKind.MATCHUPS,
        scope_key=ScopeKey.from_parts(EndpointKind.MATCHUPS, SEASON_ID, 8),
        path="/league/123/matchups/8",
        parameters={"sport": "nfl"},
        week=8,
    )


def _values(values: list[Any]) -> Iterator[Any]:
    return iter(values)


def _client(
    transport: StubTransport,
    *,
    base_url: str = "https://source.example/v1/",
    timeout_seconds: float = 7,
) -> SleeperSourceClient:
    timestamps = _values([REQUESTED_AT, COMPLETED_AT])
    monotonic_values = _values([10.0, 10.025])
    return SleeperSourceClient(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        transport=transport,
        clock=lambda: next(timestamps),
        monotonic_clock=lambda: next(monotonic_values),
    )


def test_successful_attempt_captures_decimal_first_canonical_receipt() -> None:
    response = StubResponse(200, b'{"z":2,"score":123.4500,"a":1}')
    transport = StubTransport(response)
    client = _client(transport)

    result = client.execute(_endpoint())

    expected_payload = {"z": 2, "score": Decimal("123.4500"), "a": 1}
    canonical = canonical_json_bytes(expected_payload)
    assert result.outcome == "succeeded"
    assert result.payload == expected_payload
    assert result.raw_sha256 == hashlib.sha256(canonical).hexdigest()
    assert result.byte_length == len(canonical)
    assert result.media_type == "application/json"
    assert result.requested_at == REQUESTED_AT
    assert result.completed_at == COMPLETED_AT
    assert result.latency_ms == 25
    assert len(transport.calls) == 1
    assert transport.calls[0] == {
        "url": "https://source.example/v1/league/123/matchups/8",
        "params": {"sport": "nfl"},
        "headers": {"User-Agent": "aidam-datalayer"},
        "timeout": 7,
        "allow_redirects": False,
    }


def test_successful_payload_round_trips_through_local_store(
    tmp_path: Path,
) -> None:
    transport = StubTransport(StubResponse(200, b'{"score":12.3400,"week":8}'))
    result = _client(transport).execute(_endpoint())
    assert result.outcome == "succeeded"
    canonical = canonical_json_bytes(result.payload)
    store = LocalDatalayerFileStore(tmp_path)

    receipt = store.store_bytes(LocalArtifactKind.PAYLOAD, canonical)
    opened = store.open_verified(
        receipt.storage_key,
        expected_sha256=result.raw_sha256,
        expected_byte_length=result.byte_length,
    )

    assert receipt.sha256 == result.raw_sha256
    assert opened.path.read_bytes() == canonical


def test_transport_failure_is_sanitized_and_not_retried() -> None:
    transport = StubTransport(
        requests.ConnectionError("secret.internal.example token=private")
    )
    result = _client(transport).execute(_endpoint())

    assert result.outcome == "failed"
    assert result.status is RequestStatus.TRANSPORT_ERROR
    assert result.http_status is None
    assert len(transport.calls) == 1
    serialized = result.model_dump_json()
    assert "secret.internal.example" not in serialized
    assert "private" not in serialized


@pytest.mark.parametrize("status", [301, 404, 503])
def test_http_failure_does_not_read_or_record_response_body(status: int) -> None:
    response = StubResponse(status, b"secret provider response body")
    transport = StubTransport(response)

    result = _client(transport).execute(_endpoint())

    assert result.outcome == "failed"
    assert result.status is RequestStatus.HTTP_ERROR
    assert result.http_status == status
    assert response.content_reads == 0
    assert "secret provider response body" not in result.model_dump_json()


@pytest.mark.parametrize(
    "content",
    [b"", b"not json", b'{"score":NaN}', b'{"score":Infinity}'],
)
def test_invalid_json_is_a_recordable_sanitized_failure(content: bytes) -> None:
    transport = StubTransport(StubResponse(200, content))

    result = _client(transport).execute(_endpoint())

    assert result.outcome == "failed"
    assert result.status is RequestStatus.INVALID_PAYLOAD
    assert result.http_status == 200
    assert result.error.code == "sleeper_invalid_json"
    if content:
        assert content.decode(errors="ignore") not in result.model_dump_json()


@pytest.mark.parametrize(
    "base_url",
    [
        "api.sleeper.app/v1",
        "ftp://api.sleeper.app/v1",
        "https://user:password@api.sleeper.app/v1",
        "https://api.sleeper.app/v1?token=secret",
        "https://api.sleeper.app/has space",
    ],
)
def test_client_rejects_unsafe_base_urls(base_url: str) -> None:
    with pytest.raises(ValueError):
        SleeperSourceClient(
            base_url=base_url,
            transport=StubTransport(StubResponse(200, b"{}")),
        )


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan")])
def test_client_rejects_invalid_timeout(timeout: float) -> None:
    with pytest.raises(ValueError):
        SleeperSourceClient(
            timeout_seconds=timeout,
            transport=StubTransport(StubResponse(200, b"{}")),
        )


def test_client_closes_only_an_internally_owned_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned = StubTransport(StubResponse(200, b"{}"))
    monkeypatch.setattr(
        "backend.services.datalayer.sleeper.client.requests.Session",
        lambda: owned,
    )
    owned_client = SleeperSourceClient()
    injected = StubTransport(StubResponse(200, b"{}"))
    injected_client = SleeperSourceClient(transport=injected)

    owned_client.close()
    injected_client.close()

    assert owned.closed is True
    assert injected.closed is False
