"""Immutable records produced by Sleeper endpoint-family normalizers."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    StringConstraints,
    model_validator,
)

from backend.services.datalayer.canonical_json import JsonValue
from backend.services.datalayer.sleeper.scope import EndpointKind


CompletenessReason = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    ),
]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]


class _EndpointValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class CompletenessFinding(_EndpointValue):
    """Whether a parsed payload is authoritative for its requested scope."""

    is_complete: StrictBool
    reason: CompletenessReason | None = None

    @model_validator(mode="after")
    def validate_reason(self) -> "CompletenessFinding":
        if self.is_complete and self.reason is not None:
            raise ValueError("a complete payload cannot have an incomplete reason")
        if not self.is_complete and self.reason is None:
            raise ValueError("an incomplete payload requires a reason")
        return self


class LeagueRecord(_EndpointValue):
    sleeper_league_id: StrictStr
    name: StrictStr
    status: StrictStr | None = None
    season: StrictStr
    previous_sleeper_league_id: StrictStr | None = None
    sleeper_draft_id: StrictStr | None = None
    sport: StrictStr
    scoring_settings: dict[str, JsonValue]
    roster_positions: tuple[StrictStr, ...]
    provider_settings: dict[str, JsonValue]
    playoff_start_week: PositiveInt | None = None
    playoff_team_count: PositiveInt | None = None
    league_average_match: NonNegativeInt | None = None


class UserRecord(_EndpointValue):
    sleeper_user_id: StrictStr
    display_name: StrictStr
    username: StrictStr | None = None
    avatar: StrictStr | None = None
    metadata: dict[str, JsonValue]


class LeagueUserRecord(_EndpointValue):
    sleeper_user_id: StrictStr
    team_name: StrictStr | None = None
    nickname: StrictStr | None = None
    is_commissioner: StrictBool = False
    metadata: dict[str, JsonValue]


class NflStateRecord(_EndpointValue):
    sport: Literal["nfl"] = "nfl"
    week: NonNegativeInt
    leg: NonNegativeInt | None = None
    season_type: StrictStr | None = None
    season_start_date: StrictStr | None = None
    season: StrictStr
    previous_season: StrictStr | None = None
    league_season: StrictStr | None = None
    league_create_season: StrictStr | None = None
    display_week: NonNegativeInt | None = None
    provider_state: dict[str, JsonValue]


class PlayerRecord(_EndpointValue):
    sleeper_player_id: StrictStr
    full_name: StrictStr | None = None
    position: StrictStr | None = None
    nfl_team: StrictStr | None = None
    active: StrictBool | None = None
    status: StrictStr | None = None
    injury_status: StrictStr | None = None
    age: NonNegativeInt | None = None
    years_experience: NonNegativeInt | None = None
    metadata: dict[str, JsonValue]


class LeagueEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.LEAGUE] = EndpointKind.LEAGUE
    league: LeagueRecord


class LeagueUsersEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.LEAGUE_USERS] = EndpointKind.LEAGUE_USERS
    users: tuple[UserRecord, ...]
    league_users: tuple[LeagueUserRecord, ...]


class NflStateEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.NFL_STATE] = EndpointKind.NFL_STATE
    state: NflStateRecord


class PlayerCatalogEndpointRecords(_EndpointValue):
    endpoint_kind: Literal[EndpointKind.PLAYER_CATALOG] = EndpointKind.PLAYER_CATALOG
    players: tuple[PlayerRecord, ...]


EndpointRecords: TypeAlias = Annotated[
    LeagueEndpointRecords
    | LeagueUsersEndpointRecords
    | NflStateEndpointRecords
    | PlayerCatalogEndpointRecords,
    Field(discriminator="endpoint_kind"),
]
