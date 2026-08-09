"""Canonical Sleeper endpoint identity and scope keys."""

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
