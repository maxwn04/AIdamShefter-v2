"""Sleeper roster endpoint request, completeness, and normalization."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Never
from uuid import UUID

from ...canonical_json import JsonValue
from ...errors import EndpointPayloadRejected
from ..responses import CompletenessFinding, EndpointRequest
from ..scope import EndpointKind, ScopeKey

RosterRole = Literal["starter", "bench", "taxi", "reserve", "ir"]
ManagerRole = Literal["owner", "co_owner"]


@dataclass(frozen=True, slots=True)
class RosterRecord:
    sleeper_roster_id: str
    settings: dict[str, JsonValue]
    metadata: dict[str, JsonValue]
    record_string: str | None
    wins: int
    losses: int
    ties: int
    points_for: Decimal
    points_against: Decimal


@dataclass(frozen=True, slots=True)
class RosterManagerRecord:
    sleeper_roster_id: str
    sleeper_user_id: str
    role: ManagerRole
    source_order: int


@dataclass(frozen=True, slots=True)
class RosterPlayerRecord:
    sleeper_roster_id: str
    sleeper_player_id: str
    role: RosterRole


@dataclass(frozen=True, slots=True)
class RosterEndpointRecords:
    rosters: tuple[RosterRecord, ...]
    managers: tuple[RosterManagerRecord, ...]
    players: tuple[RosterPlayerRecord, ...]


@dataclass(frozen=True, slots=True)
class TradedPickRecord:
    draft_season_year: int
    draft_round: int
    original_sleeper_roster_id: str
    current_owner_sleeper_roster_id: str
    sleeper_pick_id: str | None


def build_rosters_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
) -> EndpointRequest:
    """Build the one authoritative roster request for a competition season."""

    league_id = _nonempty_identifier(sleeper_league_id, field="sleeper_league_id")
    return EndpointRequest(
        endpoint_kind=EndpointKind.LEAGUE_ROSTERS,
        scope_key=ScopeKey.from_parts("rosters", competition_season_id),
        path=f"/league/{league_id}/rosters",
    )


def build_traded_picks_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
) -> EndpointRequest:
    """Build the authoritative traded-pick request for a competition season."""

    league_id = _nonempty_identifier(sleeper_league_id, field="sleeper_league_id")
    return EndpointRequest(
        endpoint_kind=EndpointKind.TRADED_PICKS,
        scope_key=ScopeKey.from_parts("traded_picks", competition_season_id),
        path=f"/league/{league_id}/traded_picks",
    )


def validate_rosters_completeness(payload: JsonValue) -> CompletenessFinding:
    """Return whether the payload has the minimum authoritative roster shape."""

    if not isinstance(payload, list):
        return CompletenessFinding(
            is_complete=False,
            code="payload_not_array",
            summary="Sleeper roster payload must be an array",
        )
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            return CompletenessFinding(
                is_complete=False,
                code="roster_not_object",
                summary=f"Sleeper roster at index {index} must be an object",
            )
        if item.get("roster_id") is None:
            return CompletenessFinding(
                is_complete=False,
                code="roster_id_missing",
                summary=f"Sleeper roster at index {index} has no roster_id",
            )
    return CompletenessFinding(
        is_complete=True,
        code="complete",
        summary="Sleeper roster payload is complete",
    )


def validate_traded_picks_completeness(payload: JsonValue) -> CompletenessFinding:
    """Treat a valid list, including an empty one, as authoritative."""

    if not isinstance(payload, list):
        return CompletenessFinding(
            is_complete=False,
            code="traded_picks_payload_not_array",
            summary="Sleeper traded-pick payload must be an array",
        )
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            return CompletenessFinding(
                is_complete=False,
                code="traded_pick_not_object",
                summary=f"Sleeper traded pick at index {index} must be an object",
            )
    return CompletenessFinding(
        is_complete=True,
        code="complete",
        summary="Sleeper traded-pick payload is complete",
    )


def normalize_rosters(payload: JsonValue) -> RosterEndpointRecords:
    """Normalize one complete roster payload without persistence concerns."""

    finding = validate_rosters_completeness(payload)
    if not finding.is_complete:
        _reject(finding.code, finding.summary)
    assert isinstance(payload, list)

    roster_rows: list[tuple[int, RosterRecord]] = []
    manager_rows: list[tuple[int, RosterManagerRecord]] = []
    player_rows: list[tuple[int, RosterPlayerRecord]] = []
    seen_rosters: set[int] = set()

    for index, value in enumerate(payload):
        assert isinstance(value, dict)
        roster_id = _required_int(value.get("roster_id"), f"roster[{index}].roster_id")
        if roster_id in seen_rosters:
            _reject(
                "duplicate_roster",
                f"Sleeper roster payload repeats roster_id {roster_id}",
            )
        seen_rosters.add(roster_id)
        sleeper_roster_id = str(roster_id)

        settings = _object_or_empty(value.get("settings"), f"roster[{index}].settings")
        metadata = _object_or_empty(value.get("metadata"), f"roster[{index}].metadata")
        roster_rows.append(
            (
                roster_id,
                RosterRecord(
                    sleeper_roster_id=sleeper_roster_id,
                    settings=settings,
                    metadata=metadata,
                    record_string=_record_string(metadata.get("record"), index=index),
                    wins=_integer_setting(settings, "wins", index=index),
                    losses=_integer_setting(settings, "losses", index=index),
                    ties=_integer_setting(settings, "ties", index=index),
                    points_for=_points_from_settings(settings, "fpts", index=index),
                    points_against=_points_from_settings(
                        settings, "fpts_against", index=index
                    ),
                ),
            )
        )

        manager_rows.extend(
            (roster_id, row)
            for row in _normalize_managers(
                value,
                sleeper_roster_id=sleeper_roster_id,
                index=index,
            )
        )
        player_rows.extend(
            (roster_id, row)
            for row in _normalize_players(
                value,
                sleeper_roster_id=sleeper_roster_id,
                index=index,
            )
        )

    return RosterEndpointRecords(
        rosters=tuple(row for _, row in sorted(roster_rows, key=lambda item: item[0])),
        managers=tuple(
            row
            for _, row in sorted(
                manager_rows,
                key=lambda item: (item[0], item[1].source_order, item[1].sleeper_user_id),
            )
        ),
        players=tuple(
            row
            for _, row in sorted(
                player_rows,
                key=lambda item: (item[0], item[1].sleeper_player_id),
            )
        ),
    )


def normalize_traded_picks(payload: JsonValue) -> tuple[TradedPickRecord, ...]:
    """Normalize current pick ownership in stable natural-coordinate order."""

    finding = validate_traded_picks_completeness(payload)
    if not finding.is_complete:
        _reject(
            finding.code,
            finding.summary,
            endpoint_kind=EndpointKind.TRADED_PICKS,
        )
    assert isinstance(payload, list)

    records: list[tuple[tuple[int, int, int], TradedPickRecord]] = []
    seen_coordinates: set[tuple[int, int, int]] = set()
    for index, value in enumerate(payload):
        assert isinstance(value, dict)
        field_prefix = f"traded_pick[{index}]"
        season = _required_int(
            value.get("season"),
            f"{field_prefix}.season",
            endpoint_kind=EndpointKind.TRADED_PICKS,
        )
        round_number = _required_int(
            value.get("round"),
            f"{field_prefix}.round",
            endpoint_kind=EndpointKind.TRADED_PICKS,
        )
        original_roster = _required_int(
            value.get("roster_id"),
            f"{field_prefix}.roster_id",
            endpoint_kind=EndpointKind.TRADED_PICKS,
        )
        current_owner = _required_int(
            value.get("owner_id"),
            f"{field_prefix}.owner_id",
            endpoint_kind=EndpointKind.TRADED_PICKS,
        )
        if min(season, round_number, original_roster, current_owner) < 1:
            _reject(
                "traded_pick_coordinate_not_positive",
                f"Sleeper traded pick at index {index} has a non-positive coordinate",
                endpoint_kind=EndpointKind.TRADED_PICKS,
            )

        coordinate = (season, round_number, original_roster)
        if coordinate in seen_coordinates:
            _reject(
                "duplicate_traded_pick",
                "Sleeper traded-pick payload repeats a natural pick coordinate",
                endpoint_kind=EndpointKind.TRADED_PICKS,
            )
        seen_coordinates.add(coordinate)

        pick_value = value.get("draft_pick_id")
        sleeper_pick_id = None
        if pick_value is not None:
            sleeper_pick_id = _identifier(
                pick_value,
                f"{field_prefix}.draft_pick_id",
                endpoint_kind=EndpointKind.TRADED_PICKS,
            )
        records.append(
            (
                coordinate,
                TradedPickRecord(
                    draft_season_year=season,
                    draft_round=round_number,
                    original_sleeper_roster_id=str(original_roster),
                    current_owner_sleeper_roster_id=str(current_owner),
                    sleeper_pick_id=sleeper_pick_id,
                ),
            )
        )
    return tuple(record for _, record in sorted(records, key=lambda item: item[0]))


def _normalize_managers(
    roster: dict[str, JsonValue],
    *,
    sleeper_roster_id: str,
    index: int,
) -> tuple[RosterManagerRecord, ...]:
    rows: list[RosterManagerRecord] = []
    seen_users: set[str] = set()
    owner = roster.get("owner_id")
    if owner is not None:
        owner_id = _identifier(owner, f"roster[{index}].owner_id")
        rows.append(
            RosterManagerRecord(
                sleeper_roster_id=sleeper_roster_id,
                sleeper_user_id=owner_id,
                role="owner",
                source_order=0,
            )
        )
        seen_users.add(owner_id)

    co_owners = roster.get("co_owners")
    if co_owners is None:
        return tuple(rows)
    if not isinstance(co_owners, list):
        _reject(
            "co_owners_not_array",
            f"Sleeper roster at index {index} has a non-array co_owners value",
        )
    for source_order, value in enumerate(co_owners, start=1):
        user_id = _identifier(value, f"roster[{index}].co_owners[{source_order - 1}]")
        if user_id in seen_users:
            continue
        rows.append(
            RosterManagerRecord(
                sleeper_roster_id=sleeper_roster_id,
                sleeper_user_id=user_id,
                role="co_owner",
                source_order=source_order,
            )
        )
        seen_users.add(user_id)
    return tuple(rows)


def _normalize_players(
    roster: dict[str, JsonValue],
    *,
    sleeper_roster_id: str,
    index: int,
) -> tuple[RosterPlayerRecord, ...]:
    memberships = {
        field: set(_identifier_list(roster.get(field), f"roster[{index}].{field}"))
        for field in ("players", "starters", "taxi", "reserve", "ir")
    }
    all_players = set().union(*memberships.values())
    role_priority: tuple[tuple[RosterRole, str], ...] = (
        ("starter", "starters"),
        ("taxi", "taxi"),
        ("reserve", "reserve"),
        ("ir", "ir"),
    )
    rows: list[RosterPlayerRecord] = []
    for player_id in sorted(all_players):
        role: RosterRole = "bench"
        for candidate, field in role_priority:
            if player_id in memberships[field]:
                role = candidate
                break
        rows.append(
            RosterPlayerRecord(
                sleeper_roster_id=sleeper_roster_id,
                sleeper_player_id=player_id,
                role=role,
            )
        )
    return tuple(rows)


def _points_from_settings(
    settings: dict[str, JsonValue],
    prefix: str,
    *,
    index: int,
) -> Decimal:
    whole = _decimal_or_zero(settings.get(prefix), f"roster[{index}].settings.{prefix}")
    decimal = _decimal_or_zero(
        settings.get(f"{prefix}_decimal"),
        f"roster[{index}].settings.{prefix}_decimal",
    )
    return whole + decimal / Decimal(100)


def _integer_setting(
    settings: dict[str, JsonValue],
    name: str,
    *,
    index: int,
) -> int:
    value = settings.get(name)
    if value is None:
        return 0
    return _required_int(value, f"roster[{index}].settings.{name}")


def _record_string(value: JsonValue | None, *, index: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for position, item in enumerate(value):
            if item is None:
                continue
            if not isinstance(item, (str, int, Decimal)) or isinstance(item, bool):
                _reject(
                    "invalid_record_string",
                    f"Sleeper roster at index {index} has an invalid record item at {position}",
                )
            parts.append(str(item))
        return "".join(parts)
    _reject(
        "invalid_record_string",
        f"Sleeper roster at index {index} has an invalid metadata.record value",
    )


def _identifier_list(value: JsonValue | None, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        _reject("identifier_list_not_array", f"{field} must be an array")
    return tuple(_identifier(item, f"{field}[{index}]") for index, item in enumerate(value))


def _object_or_empty(value: JsonValue | None, field: str) -> dict[str, JsonValue]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        _reject("object_expected", f"{field} must be an object")
    return dict(value)


def _required_int(
    value: JsonValue | None,
    field: str,
    *,
    endpoint_kind: EndpointKind = EndpointKind.LEAGUE_ROSTERS,
) -> int:
    if isinstance(value, bool) or value is None:
        _reject(
            "integer_expected",
            f"{field} must be an integer",
            endpoint_kind=endpoint_kind,
        )
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    _reject(
        "integer_expected",
        f"{field} must be an integer",
        endpoint_kind=endpoint_kind,
    )


def _decimal_or_zero(value: JsonValue | None, field: str) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, bool) or isinstance(value, float):
        _reject("decimal_expected", f"{field} must be an exact decimal number")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        _reject("decimal_expected", f"{field} must be an exact decimal number")
    if not result.is_finite():
        _reject("decimal_expected", f"{field} must be a finite decimal number")
    return result


def _identifier(
    value: JsonValue,
    field: str,
    *,
    endpoint_kind: EndpointKind = EndpointKind.LEAGUE_ROSTERS,
) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        _reject(
            "identifier_expected",
            f"{field} must be an identifier",
            endpoint_kind=endpoint_kind,
        )
    result = str(value).strip()
    if not result:
        _reject(
            "identifier_expected",
            f"{field} must be a non-empty identifier",
            endpoint_kind=endpoint_kind,
        )
    return result


def _nonempty_identifier(value: str, *, field: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError(f"{field} must not be empty")
    if any(character in result for character in "/?#"):
        raise ValueError(f"{field} contains a path delimiter")
    return result


def _reject(
    code: str,
    summary: str,
    *,
    endpoint_kind: EndpointKind = EndpointKind.LEAGUE_ROSTERS,
) -> Never:
    raise EndpointPayloadRejected(
        endpoint_kind=endpoint_kind,
        code=code,
        summary=summary,
    )
