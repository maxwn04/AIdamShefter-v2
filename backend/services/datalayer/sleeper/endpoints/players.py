"""Sleeper global player-catalog endpoint behavior."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Never, cast

from ...canonical_json import JsonValue
from ...errors import EndpointPayloadRejected
from ..responses import CompletenessFinding, EndpointRequest
from ..scope import EndpointKind, ScopeKey


@dataclass(frozen=True, slots=True)
class PlayerRecord:
    """Normalized current player metadata from one complete catalog."""

    sleeper_player_id: str
    full_name: str | None
    position: str | None
    nfl_team: str | None
    active: bool | None
    status: str | None
    injury_status: str | None
    age: int | None
    years_experience: int | None
    metadata: dict[str, JsonValue]


def build_player_catalog_request(*, sport: str = "nfl") -> EndpointRequest:
    """Construct the exact global player-catalog request and scope."""

    normalized_sport = _path_segment(sport.strip().lower(), "sport")
    scope_key = ScopeKey.from_parts("players", normalized_sport)
    return EndpointRequest(
        endpoint_kind=EndpointKind.PLAYER_CATALOG,
        scope_key=scope_key,
        path=f"/players/{normalized_sport}",
    )


def validate_player_catalog_completeness(payload: JsonValue) -> CompletenessFinding:
    """Reject empty, truncated, or structurally invalid catalog responses."""

    try:
        normalize_player_catalog(payload)
    except EndpointPayloadRejected as rejection:
        return CompletenessFinding(
            is_complete=False,
            code=rejection.code,
            summary=rejection.summary,
        )
    return CompletenessFinding(
        is_complete=True,
        code="player_catalog_payload_complete",
        summary="Sleeper returned a complete player catalog",
    )


def normalize_player_catalog(payload: JsonValue) -> tuple[PlayerRecord, ...]:
    """Normalize a complete catalog in deterministic player-ID order."""

    if not isinstance(payload, dict):
        _reject(
            "player_catalog_payload_not_object",
            "Sleeper player catalog must be a JSON object",
        )
    raw_catalog = cast(dict[str, JsonValue], payload)
    if not raw_catalog:
        _reject(
            "player_catalog_empty",
            "Sleeper player catalog is unexpectedly empty",
        )

    records: list[PlayerRecord] = []
    for catalog_player_id in sorted(raw_catalog):
        raw_player = raw_catalog[catalog_player_id]
        if not isinstance(raw_player, dict):
            _reject(
                "player_record_not_object",
                f"Sleeper player {catalog_player_id} must be a JSON object",
            )
        records.append(
            _normalize_player(
                catalog_player_id,
                cast(dict[str, JsonValue], raw_player),
            )
        )
    return tuple(records)


def _normalize_player(
    catalog_player_id: str,
    raw: dict[str, JsonValue],
) -> PlayerRecord:
    if not catalog_player_id.strip():
        _reject("player_id_missing", "Sleeper player catalog contains an empty ID")
    payload_player_id = raw.get("player_id")
    if payload_player_id is not None:
        if not isinstance(payload_player_id, str) or not payload_player_id.strip():
            _reject(
                "player_id_invalid",
                f"Sleeper player {catalog_player_id} has an invalid player_id",
            )
        if payload_player_id != catalog_player_id:
            _reject(
                "player_id_mismatch",
                f"Sleeper player {catalog_player_id} does not match its catalog key",
            )

    status = _optional_text(raw.get("status"), catalog_player_id, "status")
    return PlayerRecord(
        sleeper_player_id=catalog_player_id,
        full_name=_full_name(raw, catalog_player_id),
        position=_optional_text(raw.get("position"), catalog_player_id, "position"),
        nfl_team=_optional_text(raw.get("team"), catalog_player_id, "team"),
        active=_active(raw.get("active"), status, catalog_player_id),
        status=status,
        injury_status=_optional_text(
            raw.get("injury_status"), catalog_player_id, "injury_status"
        ),
        age=_optional_int(raw.get("age"), catalog_player_id, "age"),
        years_experience=_optional_int(
            raw.get("years_exp"), catalog_player_id, "years_exp"
        ),
        metadata=dict(raw),
    )


def _full_name(raw: dict[str, JsonValue], player_id: str) -> str | None:
    full_name = _optional_text(raw.get("full_name"), player_id, "full_name")
    if full_name:
        return full_name
    first_name = _optional_text(raw.get("first_name"), player_id, "first_name")
    last_name = _optional_text(raw.get("last_name"), player_id, "last_name")
    if first_name and last_name:
        return f"{first_name} {last_name}"
    return first_name or last_name


def _active(
    value: JsonValue | None,
    status: str | None,
    player_id: str,
) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is not None:
        _reject(
            "player_active_invalid",
            f"Sleeper player {player_id} active must be boolean or null",
        )
    if status is None:
        return None
    normalized_status = status.strip().lower()
    if normalized_status == "active":
        return True
    if normalized_status in {"inactive", "retired"}:
        return False
    return None


def _optional_text(
    value: JsonValue | None,
    player_id: str,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _reject(
            f"player_{field_name}_invalid",
            f"Sleeper player {player_id} {field_name} must be text or null",
        )
    return value


def _optional_int(
    value: JsonValue | None,
    player_id: str,
    field_name: str,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        _reject_integer(player_id, field_name)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    _reject_integer(player_id, field_name)


def _reject_integer(player_id: str, field_name: str) -> Never:
    _reject(
        f"player_{field_name}_invalid",
        f"Sleeper player {player_id} {field_name} must be an integer or null",
    )


def _path_segment(value: str, field_name: str) -> str:
    if not value or any(
        character
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for character in value
    ):
        raise ValueError(f"{field_name} must be a safe non-empty path segment")
    return value


def _reject(code: str, summary: str) -> Never:
    raise EndpointPayloadRejected(
        endpoint_kind=EndpointKind.PLAYER_CATALOG,
        code=code,
        summary=summary,
    )
