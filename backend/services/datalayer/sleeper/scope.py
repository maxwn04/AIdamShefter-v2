"""Canonical Sleeper endpoint kinds and deterministic scope identities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Self
from uuid import UUID


_SCOPE_PART = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


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


ScopePart = str | int | UUID | EndpointKind


@dataclass(frozen=True, slots=True)
class ScopeKey:
    """Validated stable identity for one complete endpoint response scope."""

    value: str

    def __post_init__(self) -> None:
        parts = self.value.split(":")
        if len(parts) < 2 or any(not _SCOPE_PART.fullmatch(part) for part in parts):
            raise ValueError(f"invalid scope key: {self.value!r}")

    @classmethod
    def from_parts(cls, *parts: ScopePart) -> Self:
        if len(parts) < 2:
            raise ValueError("a scope key requires at least two parts")
        if any(isinstance(part, bool) for part in parts):
            raise TypeError("boolean values are not valid scope-key parts")
        return cls(":".join(str(part) for part in parts))

    @classmethod
    def parse(cls, value: str) -> Self:
        """Validate a scope key loaded at a persistence or transport boundary."""

        return cls(value)

    def __str__(self) -> str:
        return self.value
