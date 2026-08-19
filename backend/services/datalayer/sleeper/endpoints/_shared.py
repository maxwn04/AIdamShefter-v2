"""Small parsing helpers shared by pure Sleeper endpoint families."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import NoReturn, cast
from uuid import UUID

from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints.contracts import (
    CompletenessFinding,
)
from backend.services.datalayer.sleeper.scope import EndpointKind


_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")


def validated_season_id(value: UUID) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError("competition season ID must be a UUID")
    return value


def validated_league_id(value: str) -> str:
    if not isinstance(value, str) or not _PATH_SEGMENT.fullmatch(value):
        raise ValueError("Sleeper league ID must be a non-empty URL-safe path segment")
    return value


def validated_week(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 18:
        raise ValueError("week must be between 1 and 18")
    return value


def complete() -> CompletenessFinding:
    return CompletenessFinding(is_complete=True)


def incomplete(reason: str) -> CompletenessFinding:
    return CompletenessFinding(is_complete=False, reason=reason)


def reject(endpoint_kind: EndpointKind, code: str) -> NoReturn:
    raise EndpointPayloadRejected(
        endpoint_kind,
        code,
        f"Sleeper {endpoint_kind.value} payload is incomplete",
    )


def payload_list(
    value: JsonValue,
    endpoint_kind: EndpointKind,
    code: str,
) -> list[JsonValue]:
    if not isinstance(value, list):
        reject(endpoint_kind, code)
    return value


def payload_object(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    code: str,
    *,
    default_empty: bool = False,
) -> dict[str, JsonValue]:
    if value is None and default_empty:
        return {}
    if not isinstance(value, dict):
        reject(endpoint_kind, code)
    return dict(value)


def identifier(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    code: str,
) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        reject(endpoint_kind, code)
    result = str(value).strip()
    if not result:
        reject(endpoint_kind, code)
    return result


def optional_identifier(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    code: str,
) -> str | None:
    if value is None:
        return None
    return identifier(value, endpoint_kind, code)


def identifier_list(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    code: str,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        reject(endpoint_kind, code)
    return tuple(identifier(item, endpoint_kind, code) for item in value)


def exact_decimal(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    code: str,
    *,
    default: Decimal | None = None,
) -> Decimal:
    if value is None and default is not None:
        return default
    if isinstance(value, (bool, float)) or value is None:
        reject(endpoint_kind, code)
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        reject(endpoint_kind, code)
    if not cast(Decimal, result).is_finite():
        reject(endpoint_kind, code)
    return cast(Decimal, result)


def integer(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    code: str,
    *,
    minimum: int | None = None,
    default: int | None = None,
) -> int:
    if value is None and default is not None:
        result = default
    elif isinstance(value, bool) or value is None:
        reject(endpoint_kind, code)
    elif isinstance(value, int):
        result = value
    elif (
        isinstance(value, Decimal)
        and value.is_finite()
        and value == value.to_integral_value()
    ):
        result = int(value)
    elif isinstance(value, str):
        try:
            result = int(value)
        except ValueError:
            reject(endpoint_kind, code)
    else:
        reject(endpoint_kind, code)
    if minimum is not None and result < minimum:
        reject(endpoint_kind, code)
    return result


def optional_integer(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    code: str,
    *,
    minimum: int | None = None,
) -> int | None:
    if value is None:
        return None
    return integer(value, endpoint_kind, code, minimum=minimum)


def optional_text(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    code: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        reject(endpoint_kind, code)
    return value


def identifier_sort_key(value: str) -> tuple[int, int | str]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)
