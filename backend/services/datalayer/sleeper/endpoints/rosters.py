"""League-roster and traded-pick endpoint behavior."""

from __future__ import annotations

from decimal import Decimal
from typing import cast
from uuid import UUID

from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints._shared import (
    complete,
    exact_decimal,
    identifier,
    identifier_list,
    identifier_sort_key,
    incomplete,
    integer,
    optional_identifier,
    payload_list,
    payload_object,
    reject,
    validated_league_id,
    validated_season_id,
)
from backend.services.datalayer.sleeper.endpoints.contracts import (
    CompletenessFinding,
    LeagueRostersEndpointRecords,
    RosterManagerRecord,
    RosterPlayerRecord,
    RosterRecord,
    TradedPickRecord,
    TradedPicksEndpointRecords,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


def build_league_rosters_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
) -> EndpointRequest:
    season_id = validated_season_id(competition_season_id)
    league_id = validated_league_id(sleeper_league_id)
    return EndpointRequest(
        endpoint_kind=EndpointKind.LEAGUE_ROSTERS,
        scope_key=ScopeKey.from_parts(EndpointKind.LEAGUE_ROSTERS, season_id),
        path=f"/league/{league_id}/rosters",
    )


def build_traded_picks_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
) -> EndpointRequest:
    season_id = validated_season_id(competition_season_id)
    league_id = validated_league_id(sleeper_league_id)
    return EndpointRequest(
        endpoint_kind=EndpointKind.TRADED_PICKS,
        scope_key=ScopeKey.from_parts(EndpointKind.TRADED_PICKS, season_id),
        path=f"/league/{league_id}/traded_picks",
    )


def validate_league_rosters_completeness(
    payload: JsonValue,
    request: EndpointRequest,
) -> CompletenessFinding:
    _require_season_request(request, EndpointKind.LEAGUE_ROSTERS, "/rosters")
    try:
        _parse_rosters(payload)
    except EndpointPayloadRejected as error:
        return incomplete(error.code)
    return complete()


def validate_traded_picks_completeness(
    payload: JsonValue,
    request: EndpointRequest,
) -> CompletenessFinding:
    _require_season_request(request, EndpointKind.TRADED_PICKS, "/traded_picks")
    try:
        _parse_traded_picks(payload)
    except EndpointPayloadRejected as error:
        return incomplete(error.code)
    return complete()


def normalize_league_rosters(
    payload: JsonValue,
    request: EndpointRequest,
) -> LeagueRostersEndpointRecords:
    _require_season_request(request, EndpointKind.LEAGUE_ROSTERS, "/rosters")
    return _parse_rosters(payload)


def normalize_traded_picks(
    payload: JsonValue,
    request: EndpointRequest,
) -> TradedPicksEndpointRecords:
    _require_season_request(request, EndpointKind.TRADED_PICKS, "/traded_picks")
    return _parse_traded_picks(payload)


def _parse_rosters(payload: JsonValue) -> LeagueRostersEndpointRecords:
    kind = EndpointKind.LEAGUE_ROSTERS
    raw_rosters = payload_list(payload, kind, "league_rosters_payload_not_list")
    rosters: list[RosterRecord] = []
    managers: list[RosterManagerRecord] = []
    players: list[RosterPlayerRecord] = []
    seen_rosters: set[str] = set()

    for raw_value in raw_rosters:
        raw = payload_object(raw_value, kind, "league_roster_not_object")
        roster_id = identifier(raw.get("roster_id"), kind, "league_roster_id_missing")
        if roster_id in seen_rosters:
            reject(kind, "league_roster_id_duplicate")
        seen_rosters.add(roster_id)
        settings = payload_object(
            raw.get("settings"),
            kind,
            "league_roster_settings_invalid",
            default_empty=True,
        )
        metadata = payload_object(
            raw.get("metadata"),
            kind,
            "league_roster_metadata_invalid",
            default_empty=True,
        )
        rosters.append(
            RosterRecord(
                sleeper_roster_id=roster_id,
                settings=settings,
                metadata=metadata,
                record_string=_record_string(metadata.get("record")),
                wins=integer(
                    settings.get("wins"),
                    kind,
                    "league_roster_wins_invalid",
                    minimum=0,
                    default=0,
                ),
                losses=integer(
                    settings.get("losses"),
                    kind,
                    "league_roster_losses_invalid",
                    minimum=0,
                    default=0,
                ),
                ties=integer(
                    settings.get("ties"),
                    kind,
                    "league_roster_ties_invalid",
                    minimum=0,
                    default=0,
                ),
                points_for=_roster_points(settings, "fpts"),
                points_against=_roster_points(settings, "fpts_against"),
            )
        )
        managers.extend(_roster_managers(raw, roster_id))
        players.extend(_roster_players(raw, roster_id))

    rosters.sort(key=lambda row: identifier_sort_key(row.sleeper_roster_id))
    managers.sort(
        key=lambda row: (
            identifier_sort_key(row.sleeper_roster_id),
            row.source_order,
            row.sleeper_user_id,
        )
    )
    players.sort(
        key=lambda row: (
            identifier_sort_key(row.sleeper_roster_id),
            row.sleeper_player_id,
        )
    )
    return LeagueRostersEndpointRecords(
        rosters=tuple(rosters),
        managers=tuple(managers),
        players=tuple(players),
    )


def _parse_traded_picks(payload: JsonValue) -> TradedPicksEndpointRecords:
    kind = EndpointKind.TRADED_PICKS
    raw_picks = payload_list(payload, kind, "traded_picks_payload_not_list")
    picks: list[TradedPickRecord] = []
    coordinates: set[tuple[int, int, str]] = set()
    for raw_value in raw_picks:
        raw = payload_object(raw_value, kind, "traded_pick_not_object")
        season = integer(
            raw.get("season"), kind, "traded_pick_season_invalid", minimum=1
        )
        round_number = integer(
            raw.get("round"), kind, "traded_pick_round_invalid", minimum=1
        )
        original_roster = identifier(
            raw.get("roster_id"), kind, "traded_pick_original_roster_invalid"
        )
        current_owner = identifier(
            raw.get("owner_id"), kind, "traded_pick_owner_invalid"
        )
        coordinate = (season, round_number, original_roster)
        if coordinate in coordinates:
            reject(kind, "traded_pick_coordinate_duplicate")
        coordinates.add(coordinate)
        picks.append(
            TradedPickRecord(
                draft_season_year=season,
                draft_round=round_number,
                original_sleeper_roster_id=original_roster,
                current_owner_sleeper_roster_id=current_owner,
                sleeper_pick_id=optional_identifier(
                    raw.get("draft_pick_id"), kind, "traded_pick_id_invalid"
                ),
            )
        )
    picks.sort(
        key=lambda row: (
            row.draft_season_year,
            row.draft_round,
            identifier_sort_key(row.original_sleeper_roster_id),
        )
    )
    return TradedPicksEndpointRecords(picks=tuple(picks))


def _roster_managers(
    raw: dict[str, JsonValue],
    roster_id: str,
) -> list[RosterManagerRecord]:
    kind = EndpointKind.LEAGUE_ROSTERS
    result: list[RosterManagerRecord] = []
    seen: set[str] = set()
    owner = optional_identifier(raw.get("owner_id"), kind, "roster_owner_invalid")
    if owner is not None:
        result.append(
            RosterManagerRecord(
                sleeper_roster_id=roster_id,
                sleeper_user_id=owner,
                role="owner",
                source_order=0,
            )
        )
        seen.add(owner)
    co_owners = identifier_list(
        raw.get("co_owners"), kind, "roster_co_owners_invalid"
    )
    for source_order, user_id in enumerate(co_owners, start=1):
        if user_id in seen:
            continue
        seen.add(user_id)
        result.append(
            RosterManagerRecord(
                sleeper_roster_id=roster_id,
                sleeper_user_id=user_id,
                role="co_owner",
                source_order=source_order,
            )
        )
    return result


def _roster_players(
    raw: dict[str, JsonValue],
    roster_id: str,
) -> list[RosterPlayerRecord]:
    kind = EndpointKind.LEAGUE_ROSTERS
    fields = {
        name: set(identifier_list(raw.get(name), kind, f"roster_{name}_invalid"))
        for name in ("players", "starters", "taxi", "reserve", "ir")
    }
    roles = (
        ("starter", "starters"),
        ("taxi", "taxi"),
        ("reserve", "reserve"),
        ("ir", "ir"),
    )
    result: list[RosterPlayerRecord] = []
    for player_id in sorted(set().union(*fields.values())):
        role = next(
            (candidate for candidate, field in roles if player_id in fields[field]),
            "bench",
        )
        result.append(
            RosterPlayerRecord(
                sleeper_roster_id=roster_id,
                sleeper_player_id=player_id,
                role=cast(str, role),
            )
        )
    return result


def _roster_points(settings: dict[str, JsonValue], prefix: str) -> Decimal:
    kind = EndpointKind.LEAGUE_ROSTERS
    whole = exact_decimal(
        settings.get(prefix),
        kind,
        f"league_roster_{prefix}_invalid",
        default=Decimal(0),
    )
    fraction = exact_decimal(
        settings.get(f"{prefix}_decimal"),
        kind,
        f"league_roster_{prefix}_decimal_invalid",
        default=Decimal(0),
    )
    result = whole + fraction / Decimal(100)
    if result < 0:
        reject(kind, f"league_roster_{prefix}_invalid")
    return result


def _record_string(value: JsonValue | None) -> str | None:
    kind = EndpointKind.LEAGUE_ROSTERS
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, bool) or not isinstance(item, (str, int, Decimal)):
                reject(kind, "league_roster_record_invalid")
            parts.append(str(item))
        return "".join(parts)
    reject(kind, "league_roster_record_invalid")


def _require_season_request(
    request: EndpointRequest,
    endpoint_kind: EndpointKind,
    suffix: str,
) -> None:
    prefix = "/league/"
    if (
        request.endpoint_kind is not endpoint_kind
        or request.parameters
        or request.week is not None
        or request.bracket_kind is not None
        or not request.path.startswith(prefix)
        or not request.path.endswith(suffix)
    ):
        raise ValueError(f"request is not a canonical {endpoint_kind.value} request")
    league_id = request.path[len(prefix) : -len(suffix)]
    validated_league_id(league_id)
    parts = request.scope_key.value.split(":")
    if len(parts) != 2 or parts[0] != endpoint_kind.value:
        raise ValueError(f"request is not a canonical {endpoint_kind.value} request")
    try:
        UUID(parts[1])
    except ValueError as error:
        raise ValueError(
            f"request is not a canonical {endpoint_kind.value} request"
        ) from error
