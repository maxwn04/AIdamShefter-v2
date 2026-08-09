"""Canonical Sleeper endpoint identity shared across backend layers."""

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Self
from uuid import UUID

_PART = re.compile(r"^[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)


class EndpointKind(StrEnum):
    LEAGUE = "league"
    LEAGUE_USERS = "league_users"
    LEAGUE_ROSTERS = "league_rosters"
    NFL_STATE = "nfl_state"
    PLAYER_CATALOG = "player_catalog"
    MATCHUPS = "matchups"
    TRANSACTIONS = "transactions"
    TRADED_PICKS = "traded_picks"
    WINNERS_BRACKET = "winners_bracket"
    LOSERS_BRACKET = "losers_bracket"


@dataclass(frozen=True, slots=True)
class ScopeKey:
    """Validated, deterministic identity for one complete endpoint response."""

    value: str

    def __post_init__(self) -> None:
        parts = self.value.split(":")
        if len(parts) < 2 or any(not _PART.fullmatch(part) for part in parts):
            raise ValueError(f"invalid scope key: {self.value!r}")

    @classmethod
    def from_parts(cls, *parts: str | int | UUID | EndpointKind) -> Self:
        if len(parts) < 2:
            raise ValueError("a scope key requires at least two parts")
        return cls(":".join(str(part) for part in parts))

    @classmethod
    def parse(cls, value: str) -> Self:
        """Validate a scope key loaded from persistence."""

        return cls(value)

    def __str__(self) -> str:
        return self.value


def expected_scope_key(
    endpoint_kind: EndpointKind,
    competition_season_id: UUID,
    *,
    week: int | None = None,
    bracket_kind: str | None = None,
) -> ScopeKey:
    """Derive the only valid scope for endpoint metadata in V1."""

    if endpoint_kind is EndpointKind.NFL_STATE:
        _require_no_endpoint_qualifiers(week, bracket_kind)
        return ScopeKey.from_parts("state", "nfl")
    if endpoint_kind is EndpointKind.PLAYER_CATALOG:
        _require_no_endpoint_qualifiers(week, bracket_kind)
        return ScopeKey.from_parts("players", "nfl")
    if endpoint_kind in (EndpointKind.MATCHUPS, EndpointKind.TRANSACTIONS):
        if week is None or not 1 <= week <= 18 or bracket_kind is not None:
            raise ValueError("weekly endpoint scope requires one valid week")
        prefix = "matchups" if endpoint_kind is EndpointKind.MATCHUPS else "transactions"
        return ScopeKey.from_parts(prefix, competition_season_id, week)
    if endpoint_kind in (EndpointKind.WINNERS_BRACKET, EndpointKind.LOSERS_BRACKET):
        expected_bracket = (
            "winners"
            if endpoint_kind is EndpointKind.WINNERS_BRACKET
            else "losers"
        )
        if week is not None or bracket_kind != expected_bracket:
            raise ValueError("bracket endpoint metadata does not match its kind")
        return ScopeKey.from_parts("bracket", competition_season_id, expected_bracket)

    _require_no_endpoint_qualifiers(week, bracket_kind)
    prefix = {
        EndpointKind.LEAGUE: "league",
        EndpointKind.LEAGUE_USERS: "users",
        EndpointKind.LEAGUE_ROSTERS: "rosters",
        EndpointKind.TRADED_PICKS: "traded_picks",
    }[endpoint_kind]
    return ScopeKey.from_parts(prefix, competition_season_id)


def infer_and_validate_scope_key(
    endpoint_kind: EndpointKind,
    scope_key: ScopeKey,
    competition_season_id: UUID,
) -> None:
    """Validate a persisted plan entry whose week/bracket lives in its scope."""

    parts = scope_key.value.split(":")
    week: int | None = None
    bracket_kind: str | None = None
    if endpoint_kind in (EndpointKind.MATCHUPS, EndpointKind.TRANSACTIONS):
        try:
            week = int(parts[-1])
        except (IndexError, ValueError) as error:
            raise ValueError("weekly endpoint scope has no valid week") from error
    elif endpoint_kind is EndpointKind.WINNERS_BRACKET:
        bracket_kind = "winners"
    elif endpoint_kind is EndpointKind.LOSERS_BRACKET:
        bracket_kind = "losers"
    if scope_key != expected_scope_key(
        endpoint_kind,
        competition_season_id,
        week=week,
        bracket_kind=bracket_kind,
    ):
        raise ValueError("endpoint kind and scope key do not agree")


def _require_no_endpoint_qualifiers(
    week: int | None,
    bracket_kind: str | None,
) -> None:
    if week is not None or bracket_kind is not None:
        raise ValueError("endpoint kind does not accept week or bracket metadata")
