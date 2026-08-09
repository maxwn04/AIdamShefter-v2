"""Sleeper league metadata and NFL-state endpoint behavior."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Never, cast
from uuid import UUID

from backend.json import JsonValue
from ...errors import EndpointPayloadRejected
from ..responses import CompletenessFinding, EndpointRequest
from backend.sleeper import EndpointKind, ScopeKey


@dataclass(frozen=True, slots=True)
class LeagueRecord:
    """Normalized values supplied by one complete league response."""

    sleeper_league_id: str
    season: str
    name: str
    sport: str
    status: str | None
    previous_sleeper_league_id: str | None
    sleeper_draft_id: str | None
    scoring_settings: dict[str, JsonValue]
    roster_positions: tuple[str, ...]
    provider_settings: dict[str, JsonValue]
    playoff_start_week: int | None
    playoff_team_count: int | None
    league_average_match: int | None
    draft_rounds: int | None


@dataclass(frozen=True, slots=True)
class NflStateRecord:
    """Normalized season/week provenance supplied by the NFL state endpoint."""

    sport: str
    season: str
    week: int
    season_type: str | None


@dataclass(frozen=True, slots=True)
class UserRecord:
    """Global Sleeper user profile fields observed through a league endpoint."""

    sleeper_user_id: str
    display_name: str
    username: str | None
    avatar: str | None
    metadata: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LeagueUserRecord:
    """League-local metadata for one Sleeper user."""

    sleeper_user_id: str
    team_name: str | None
    nickname: str | None
    is_commissioner: bool
    metadata: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LeagueUsersEndpointRecords:
    """Global and league-local rows supplied by one users response."""

    users: tuple[UserRecord, ...]
    league_users: tuple[LeagueUserRecord, ...]


def build_league_request(
    *,
    sleeper_league_id: str,
    competition_season_id: UUID,
) -> EndpointRequest:
    """Construct the exact request and durable scope for league metadata."""

    league_id = _path_segment(sleeper_league_id, "sleeper_league_id")
    scope_key = ScopeKey.from_parts("league", competition_season_id)
    return EndpointRequest(
        endpoint_kind=EndpointKind.LEAGUE,
        scope_key=scope_key,
        path=f"/league/{league_id}",
    )


def build_league_users_request(
    *,
    sleeper_league_id: str,
    competition_season_id: UUID,
) -> EndpointRequest:
    """Construct the authoritative league-users request and season scope."""

    league_id = _path_segment(sleeper_league_id, "sleeper_league_id")
    return EndpointRequest(
        endpoint_kind=EndpointKind.LEAGUE_USERS,
        scope_key=ScopeKey.from_parts("users", competition_season_id),
        path=f"/league/{league_id}/users",
    )


def build_nfl_state_request(*, sport: str = "nfl") -> EndpointRequest:
    """Construct the global state request for one normalized sport key."""

    normalized_sport = _path_segment(sport.strip().lower(), "sport")
    scope_key = ScopeKey.from_parts("state", normalized_sport)
    return EndpointRequest(
        endpoint_kind=EndpointKind.NFL_STATE,
        scope_key=scope_key,
        path=f"/state/{normalized_sport}",
    )


def validate_league_completeness(
    payload: JsonValue,
    *,
    expected_sleeper_league_id: str,
) -> CompletenessFinding:
    """Determine whether a response can authoritatively replace league scope."""

    try:
        normalize_league(
            payload,
            expected_sleeper_league_id=expected_sleeper_league_id,
        )
    except EndpointPayloadRejected as rejection:
        return CompletenessFinding(
            is_complete=False,
            code=rejection.code,
            summary=rejection.summary,
        )
    return CompletenessFinding(
        is_complete=True,
        code="league_payload_complete",
        summary="Sleeper returned complete league metadata",
    )


def validate_league_users_completeness(payload: JsonValue) -> CompletenessFinding:
    """Determine whether a users response authoritatively describes its scope."""

    try:
        normalize_league_users(payload)
    except EndpointPayloadRejected as rejection:
        return CompletenessFinding(
            is_complete=False,
            code=rejection.code,
            summary=rejection.summary,
        )
    return CompletenessFinding(
        is_complete=True,
        code="league_users_payload_complete",
        summary="Sleeper returned complete league user metadata",
    )


def validate_nfl_state_completeness(payload: JsonValue) -> CompletenessFinding:
    """Determine whether an NFL state response supplies season provenance."""

    try:
        normalize_nfl_state(payload)
    except EndpointPayloadRejected as rejection:
        return CompletenessFinding(
            is_complete=False,
            code=rejection.code,
            summary=rejection.summary,
        )
    return CompletenessFinding(
        is_complete=True,
        code="nfl_state_payload_complete",
        summary="Sleeper returned complete NFL state metadata",
    )


def normalize_league(
    payload: JsonValue,
    *,
    expected_sleeper_league_id: str,
) -> LeagueRecord:
    """Normalize league metadata without persistence side effects."""

    raw = _require_object(payload, EndpointKind.LEAGUE, "league_payload_not_object")
    sleeper_league_id = _required_text(
        raw.get("league_id"),
        EndpointKind.LEAGUE,
        "league_id_missing",
        "Sleeper league metadata is missing league_id",
    )
    if sleeper_league_id != expected_sleeper_league_id:
        _reject(
            EndpointKind.LEAGUE,
            "league_id_mismatch",
            "Sleeper league metadata does not match the requested league",
        )

    settings = _optional_object(raw.get("settings"), EndpointKind.LEAGUE, "settings")
    scoring_settings = _optional_object(
        raw.get("scoring_settings"), EndpointKind.LEAGUE, "scoring_settings"
    )
    roster_positions = _string_tuple(
        raw.get("roster_positions"), EndpointKind.LEAGUE, "roster_positions"
    )
    playoff_start_value = raw.get("playoff_week_start")
    if playoff_start_value is None:
        playoff_start_value = settings.get("playoff_week_start")
    playoff_team_value = raw.get("playoff_teams")
    if playoff_team_value is None:
        playoff_team_value = settings.get("playoff_teams")

    return LeagueRecord(
        sleeper_league_id=sleeper_league_id,
        season=_required_text(
            raw.get("season"),
            EndpointKind.LEAGUE,
            "league_season_missing",
            "Sleeper league metadata is missing season",
        ),
        name=_required_text(
            raw.get("name"),
            EndpointKind.LEAGUE,
            "league_name_missing",
            "Sleeper league metadata is missing name",
        ),
        sport=_required_text(
            raw.get("sport"),
            EndpointKind.LEAGUE,
            "league_sport_missing",
            "Sleeper league metadata is missing sport",
        ).lower(),
        status=_optional_text(raw.get("status"), EndpointKind.LEAGUE, "status"),
        previous_sleeper_league_id=_optional_text(
            raw.get("previous_league_id"),
            EndpointKind.LEAGUE,
            "previous_league_id",
        ),
        sleeper_draft_id=_optional_text(
            raw.get("draft_id"), EndpointKind.LEAGUE, "draft_id"
        ),
        scoring_settings=scoring_settings,
        roster_positions=roster_positions,
        provider_settings=settings,
        playoff_start_week=_optional_int(
            playoff_start_value, EndpointKind.LEAGUE, "playoff_week_start"
        ),
        playoff_team_count=_optional_int(
            playoff_team_value, EndpointKind.LEAGUE, "playoff_teams"
        ),
        league_average_match=_optional_int(
            settings.get("league_average_match"),
            EndpointKind.LEAGUE,
            "league_average_match",
        ),
        draft_rounds=_optional_int(
            settings.get("draft_rounds"), EndpointKind.LEAGUE, "draft_rounds"
        ),
    )


def normalize_league_users(payload: JsonValue) -> LeagueUsersEndpointRecords:
    """Normalize global profiles and league-local user metadata separately."""

    if not isinstance(payload, list):
        _reject(
            EndpointKind.LEAGUE_USERS,
            "league_users_payload_not_array",
            "Sleeper league users payload must be a JSON array",
        )

    users: list[UserRecord] = []
    league_users: list[LeagueUserRecord] = []
    seen_user_ids: set[str] = set()
    for index, value in enumerate(payload):
        if not isinstance(value, dict):
            _reject(
                EndpointKind.LEAGUE_USERS,
                "league_user_not_object",
                f"Sleeper league user at index {index} must be a JSON object",
            )
        raw = cast(dict[str, JsonValue], value)
        sleeper_user_id = _required_text(
            raw.get("user_id"),
            EndpointKind.LEAGUE_USERS,
            "league_user_id_missing",
            f"Sleeper league user at index {index} is missing user_id",
        )
        if sleeper_user_id in seen_user_ids:
            _reject(
                EndpointKind.LEAGUE_USERS,
                "duplicate_league_user",
                f"Sleeper league users payload repeats user {sleeper_user_id}",
            )
        seen_user_ids.add(sleeper_user_id)

        username = _optional_text(
            raw.get("username"), EndpointKind.LEAGUE_USERS, "username"
        )
        display_name = _optional_text(
            raw.get("display_name"), EndpointKind.LEAGUE_USERS, "display_name"
        )
        if not display_name:
            display_name = username
        if not display_name:
            _reject(
                EndpointKind.LEAGUE_USERS,
                "league_user_display_name_missing",
                f"Sleeper league user {sleeper_user_id} has no display name",
            )

        local_metadata = _optional_object(
            raw.get("metadata"), EndpointKind.LEAGUE_USERS, "user_metadata"
        )
        users.append(
            UserRecord(
                sleeper_user_id=sleeper_user_id,
                display_name=display_name,
                username=username,
                avatar=_optional_text(
                    raw.get("avatar"), EndpointKind.LEAGUE_USERS, "avatar"
                ),
                metadata={
                    key: item
                    for key, item in raw.items()
                    if key
                    not in {
                        "user_id",
                        "display_name",
                        "username",
                        "avatar",
                        "metadata",
                        "is_owner",
                        "is_commissioner",
                    }
                },
            )
        )
        league_users.append(
            LeagueUserRecord(
                sleeper_user_id=sleeper_user_id,
                team_name=_optional_text(
                    local_metadata.get("team_name"),
                    EndpointKind.LEAGUE_USERS,
                    "team_name",
                ),
                nickname=_optional_text(
                    local_metadata.get("nickname"),
                    EndpointKind.LEAGUE_USERS,
                    "nickname",
                ),
                is_commissioner=_commissioner(raw, sleeper_user_id),
                metadata=local_metadata,
            )
        )

    return LeagueUsersEndpointRecords(
        users=tuple(sorted(users, key=lambda record: record.sleeper_user_id)),
        league_users=tuple(
            sorted(league_users, key=lambda record: record.sleeper_user_id)
        ),
    )


def normalize_nfl_state(payload: JsonValue) -> NflStateRecord:
    """Normalize NFL state without inferring current time."""

    raw = _require_object(payload, EndpointKind.NFL_STATE, "nfl_state_payload_not_object")
    week = _optional_int(raw.get("week"), EndpointKind.NFL_STATE, "week")
    if week is None or not 0 <= week <= 18:
        _reject(
            EndpointKind.NFL_STATE,
            "nfl_state_week_invalid",
            "Sleeper NFL state has no valid week",
        )
    return NflStateRecord(
        sport=_optional_text(raw.get("sport"), EndpointKind.NFL_STATE, "sport")
        or "nfl",
        season=_required_text(
            raw.get("season"),
            EndpointKind.NFL_STATE,
            "nfl_state_season_missing",
            "Sleeper NFL state is missing season",
        ),
        week=week,
        season_type=_optional_text(
            raw.get("season_type"), EndpointKind.NFL_STATE, "season_type"
        ),
    )


def _commissioner(raw: dict[str, JsonValue], sleeper_user_id: str) -> bool:
    values: list[bool] = []
    for field_name in ("is_owner", "is_commissioner"):
        value = raw.get(field_name)
        if value is None:
            continue
        if not isinstance(value, bool):
            _reject(
                EndpointKind.LEAGUE_USERS,
                "league_user_commissioner_invalid",
                f"Sleeper league user {sleeper_user_id} has an invalid commissioner flag",
            )
        values.append(value)
    return any(values)


def _require_object(
    value: JsonValue,
    endpoint_kind: EndpointKind,
    code: str,
) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        _reject(endpoint_kind, code, "Sleeper payload must be a JSON object")
    return cast(dict[str, JsonValue], value)


def _optional_object(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    field_name: str,
) -> dict[str, JsonValue]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        _reject(
            endpoint_kind,
            f"{field_name}_invalid",
            f"Sleeper {field_name} must be a JSON object",
        )
    return dict(cast(dict[str, JsonValue], value))


def _required_text(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    code: str,
    summary: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        _reject(endpoint_kind, code, summary)
    return value


def _optional_text(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _reject(
            endpoint_kind,
            f"{field_name}_invalid",
            f"Sleeper {field_name} must be text or null",
        )
    return value


def _optional_int(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    field_name: str,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        _reject_integer(endpoint_kind, field_name)
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
    _reject_integer(endpoint_kind, field_name)


def _reject_integer(endpoint_kind: EndpointKind, field_name: str) -> Never:
    _reject(
        endpoint_kind,
        f"{field_name}_invalid",
        f"Sleeper {field_name} must be an integer or null",
    )


def _string_tuple(
    value: JsonValue | None,
    endpoint_kind: EndpointKind,
    field_name: str,
) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        _reject(
            endpoint_kind,
            f"{field_name}_invalid",
            f"Sleeper {field_name} must be a list of strings",
        )
    return tuple(cast(list[str], value))


def _path_segment(value: str, field_name: str) -> str:
    if not value or any(
        character
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for character in value
    ):
        raise ValueError(f"{field_name} must be a safe non-empty path segment")
    return value


def _reject(endpoint_kind: EndpointKind, code: str, summary: str) -> Never:
    raise EndpointPayloadRejected(
        endpoint_kind=endpoint_kind,
        code=code,
        summary=summary,
    )
