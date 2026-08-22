"""League metadata, league-user, and NFL-state endpoint behavior."""

from __future__ import annotations

import re
from typing import cast
from uuid import UUID

from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.errors import EndpointPayloadRejected
from backend.services.datalayer.sleeper.endpoints.contracts import (
    CompletenessFinding,
    LeagueEndpointRecords,
    LeagueRecord,
    LeagueUserRecord,
    LeagueUsersEndpointRecords,
    NflStateEndpointRecords,
    NflStateRecord,
    UserRecord,
)
from backend.services.datalayer.sleeper.responses import EndpointRequest
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")


def build_league_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
) -> EndpointRequest:
    season_id = _validated_season_id(competition_season_id)
    league_id = _validated_path_segment(sleeper_league_id, "Sleeper league ID")
    return EndpointRequest(
        endpoint_kind=EndpointKind.LEAGUE,
        scope_key=ScopeKey.from_parts(EndpointKind.LEAGUE, season_id),
        path=f"/league/{league_id}",
    )


def build_league_users_request(
    competition_season_id: UUID,
    sleeper_league_id: str,
) -> EndpointRequest:
    season_id = _validated_season_id(competition_season_id)
    league_id = _validated_path_segment(sleeper_league_id, "Sleeper league ID")
    return EndpointRequest(
        endpoint_kind=EndpointKind.LEAGUE_USERS,
        scope_key=ScopeKey.from_parts(
            EndpointKind.LEAGUE_USERS,
            season_id,
        ),
        path=f"/league/{league_id}/users",
    )


def build_nfl_state_request(sport: str = "nfl") -> EndpointRequest:
    _require_nfl_sport(sport)
    return EndpointRequest(
        endpoint_kind=EndpointKind.NFL_STATE,
        scope_key=ScopeKey.from_parts(EndpointKind.NFL_STATE, "nfl"),
        path="/state/nfl",
    )


def validate_league_completeness(
    payload: JsonValue,
    request: EndpointRequest,
) -> CompletenessFinding:
    if not isinstance(payload, dict):
        return _incomplete("league_payload_not_object")
    if not payload:
        return _incomplete("league_payload_empty")

    expected_league_id = _requested_league_id(request, suffix="")
    league_id = payload.get("league_id")
    if not _nonempty_string(league_id):
        return _incomplete("league_id_missing")
    if league_id != expected_league_id:
        return _incomplete("league_identity_mismatch")

    for field in ("name", "season", "sport"):
        if not _nonempty_string(payload.get(field)):
            return _incomplete(f"league_{field}_missing")
    if not isinstance(payload.get("settings"), dict):
        return _incomplete("league_settings_invalid")
    if not isinstance(payload.get("scoring_settings"), dict):
        return _incomplete("league_scoring_settings_invalid")
    roster_positions = payload.get("roster_positions")
    if not isinstance(roster_positions, list) or not roster_positions or any(
        not _nonempty_string(position) for position in roster_positions
    ):
        return _incomplete("league_roster_positions_invalid")

    if not _optional_strings_are_valid(
        payload,
        "status",
        "previous_league_id",
        "draft_id",
    ):
        return _incomplete("league_optional_string_invalid")

    settings = cast(dict[str, JsonValue], payload["settings"])
    for value in (
        payload.get("playoff_week_start", settings.get("playoff_week_start")),
        payload.get("playoff_teams", settings.get("playoff_teams")),
    ):
        if not _optional_positive_int(value):
            return _incomplete("league_setting_number_invalid")
    if not _optional_nonnegative_int(settings.get("league_average_match")):
        return _incomplete("league_setting_number_invalid")
    return _complete()


def normalize_league(
    payload: JsonValue,
    request: EndpointRequest,
) -> LeagueEndpointRecords:
    _require_complete(
        EndpointKind.LEAGUE,
        validate_league_completeness(payload, request),
    )
    raw = cast(dict[str, JsonValue], payload)
    settings = cast(dict[str, JsonValue], raw["settings"])
    return LeagueEndpointRecords(
        league=LeagueRecord(
            sleeper_league_id=cast(str, raw["league_id"]),
            name=cast(str, raw["name"]),
            status=cast(str | None, raw.get("status")),
            season=cast(str, raw["season"]),
            previous_sleeper_league_id=cast(
                str | None,
                raw.get("previous_league_id"),
            ),
            sleeper_draft_id=cast(str | None, raw.get("draft_id")),
            sport=cast(str, raw["sport"]),
            scoring_settings=dict(cast(dict[str, JsonValue], raw["scoring_settings"])),
            roster_positions=tuple(cast(list[str], raw["roster_positions"])),
            provider_settings=dict(settings),
            playoff_start_week=cast(
                int | None,
                _first_present(
                    raw.get("playoff_week_start"),
                    settings.get("playoff_week_start"),
                ),
            ),
            playoff_team_count=cast(
                int | None,
                _first_present(raw.get("playoff_teams"), settings.get("playoff_teams")),
            ),
            league_average_match=cast(int | None, settings.get("league_average_match")),
        )
    )


def validate_league_users_completeness(
    payload: JsonValue,
    request: EndpointRequest,
) -> CompletenessFinding:
    _requested_league_id(request, suffix="/users")
    if not isinstance(payload, list):
        return _incomplete("league_users_payload_not_list")

    seen_user_ids: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            return _incomplete("league_user_not_object")
        user_id = item.get("user_id")
        if not _nonempty_string(user_id):
            return _incomplete("league_user_id_missing")
        if user_id in seen_user_ids:
            return _incomplete("league_user_id_duplicate")
        seen_user_ids.add(user_id)

        display_name = item.get("display_name")
        username = item.get("username")
        if not _nonempty_string(display_name) and not _nonempty_string(username):
            return _incomplete("league_user_name_missing")
        if not _optional_strings_are_valid(item, "display_name", "username", "avatar"):
            return _incomplete("league_user_profile_invalid")
        metadata = item.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            return _incomplete("league_user_metadata_invalid")
        if isinstance(metadata, dict) and not _optional_strings_are_valid(
            metadata,
            "team_name",
            "nickname",
        ):
            return _incomplete("league_user_metadata_name_invalid")
        is_owner = item.get("is_owner")
        if is_owner is not None and not isinstance(is_owner, bool):
            return _incomplete("league_user_commissioner_invalid")
    return _complete()


def normalize_league_users(
    payload: JsonValue,
    request: EndpointRequest,
) -> LeagueUsersEndpointRecords:
    _require_complete(
        EndpointKind.LEAGUE_USERS,
        validate_league_users_completeness(payload, request),
    )
    raw_users = cast(list[JsonValue], payload)
    users: list[UserRecord] = []
    league_users: list[LeagueUserRecord] = []
    for item in sorted(
        cast(list[dict[str, JsonValue]], raw_users),
        key=lambda value: cast(str, value["user_id"]),
    ):
        metadata_value = item.get("metadata")
        metadata = dict(metadata_value) if isinstance(metadata_value, dict) else {}
        display_name = item.get("display_name") or item.get("username")
        user_id = cast(str, item["user_id"])
        users.append(
            UserRecord(
                sleeper_user_id=user_id,
                display_name=cast(str, display_name),
                username=cast(str | None, item.get("username")),
                avatar=cast(str | None, item.get("avatar")),
                metadata=metadata,
            )
        )
        league_users.append(
            LeagueUserRecord(
                sleeper_user_id=user_id,
                team_name=cast(str | None, metadata.get("team_name")),
                nickname=cast(str | None, metadata.get("nickname")),
                is_commissioner=cast(bool, item.get("is_owner") or False),
                metadata=metadata,
            )
        )
    return LeagueUsersEndpointRecords(
        users=tuple(users),
        league_users=tuple(league_users),
    )


def validate_nfl_state_completeness(
    payload: JsonValue,
    request: EndpointRequest,
) -> CompletenessFinding:
    _require_nfl_state_request(request)
    if not isinstance(payload, dict):
        return _incomplete("nfl_state_payload_not_object")
    if not payload:
        return _incomplete("nfl_state_payload_empty")
    if not _nonempty_string(payload.get("season")):
        return _incomplete("nfl_state_season_missing")
    week = payload.get("week")
    if not _nonnegative_int(week):
        return _incomplete("nfl_state_week_invalid")
    if not _optional_strings_are_valid(
        payload,
        "season_type",
        "season_start_date",
        "previous_season",
        "league_season",
        "league_create_season",
    ):
        return _incomplete("nfl_state_optional_string_invalid")
    for field in ("leg", "display_week"):
        if not _optional_nonnegative_int(payload.get(field)):
            return _incomplete(f"nfl_state_{field}_invalid")
    return _complete()


def normalize_nfl_state(
    payload: JsonValue,
    request: EndpointRequest,
) -> NflStateEndpointRecords:
    _require_complete(
        EndpointKind.NFL_STATE,
        validate_nfl_state_completeness(payload, request),
    )
    raw = cast(dict[str, JsonValue], payload)
    return NflStateEndpointRecords(
        state=NflStateRecord(
            week=cast(int, raw["week"]),
            leg=cast(int | None, raw.get("leg")),
            season_type=cast(str | None, raw.get("season_type")),
            season_start_date=cast(str | None, raw.get("season_start_date")),
            season=cast(str, raw["season"]),
            previous_season=cast(str | None, raw.get("previous_season")),
            league_season=cast(str | None, raw.get("league_season")),
            league_create_season=cast(str | None, raw.get("league_create_season")),
            display_week=cast(int | None, raw.get("display_week")),
            provider_state=dict(raw),
        )
    )


def _validated_path_segment(value: str, label: str) -> str:
    if not isinstance(value, str) or not _PATH_SEGMENT.fullmatch(value):
        raise ValueError(f"{label} must be a non-empty URL-safe path segment")
    return value


def _validated_season_id(value: UUID) -> UUID:
    if not isinstance(value, UUID):
        raise TypeError("competition season ID must be a UUID")
    return value


def _requested_league_id(request: EndpointRequest, *, suffix: str) -> str:
    expected_kind = EndpointKind.LEAGUE_USERS if suffix else EndpointKind.LEAGUE
    prefix = "/league/"
    if (
        request.endpoint_kind is not expected_kind
        or request.parameters
        or request.week is not None
        or request.bracket_kind is not None
        or not _has_season_scope(request.scope_key, expected_kind)
        or not request.path.startswith(prefix)
        or not request.path.endswith(suffix)
    ):
        raise ValueError(f"request is not a canonical {expected_kind.value} request")
    end = len(request.path) - len(suffix) if suffix else len(request.path)
    return _validated_path_segment(request.path[len(prefix) : end], "Sleeper league ID")


def _has_season_scope(scope_key: ScopeKey, endpoint_kind: EndpointKind) -> bool:
    parts = scope_key.value.split(":")
    if len(parts) != 2 or parts[0] != endpoint_kind.value:
        return False
    try:
        UUID(parts[1])
    except ValueError:
        return False
    return True


def _require_nfl_state_request(request: EndpointRequest) -> None:
    if (
        request.endpoint_kind is not EndpointKind.NFL_STATE
        or request.scope_key != ScopeKey.from_parts(EndpointKind.NFL_STATE, "nfl")
        or request.path != "/state/nfl"
        or request.parameters
        or request.week is not None
        or request.bracket_kind is not None
    ):
        raise ValueError("request is not a canonical nfl_state request")


def _require_nfl_sport(sport: str) -> None:
    if sport != "nfl":
        raise ValueError("only the nfl sport scope is supported")


def _complete() -> CompletenessFinding:
    return CompletenessFinding(is_complete=True)


def _incomplete(reason: str) -> CompletenessFinding:
    return CompletenessFinding(is_complete=False, reason=reason)


def _require_complete(
    endpoint_kind: EndpointKind,
    finding: CompletenessFinding,
) -> None:
    if not finding.is_complete:
        raise EndpointPayloadRejected(
            endpoint_kind,
            cast(str, finding.reason),
            f"Sleeper {endpoint_kind.value} payload is incomplete",
        )


def _nonempty_string(value: JsonValue | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _optional_strings_are_valid(
    value: dict[str, JsonValue],
    *fields: str,
) -> bool:
    return all(
        value.get(field) is None or isinstance(value.get(field), str)
        for field in fields
    )


def _nonnegative_int(value: JsonValue | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _optional_nonnegative_int(value: JsonValue | None) -> bool:
    return value is None or _nonnegative_int(value)


def _optional_positive_int(value: JsonValue | None) -> bool:
    return value is None or (
        isinstance(value, int) and not isinstance(value, bool) and value >= 1
    )


def _first_present(
    primary: JsonValue | None,
    fallback: JsonValue | None,
) -> JsonValue | None:
    return primary if primary is not None else fallback
