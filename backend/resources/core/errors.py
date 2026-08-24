"""Stable application failures for core competition resources."""

from __future__ import annotations

from uuid import UUID


class CoreResourceError(RuntimeError):
    """Base class for core resource failures safe at service boundaries."""


class CoreResourceNotFound(CoreResourceError):
    def __init__(self, resource_kind: str, resource_id: UUID) -> None:
        self.resource_kind = resource_kind
        self.resource_id = resource_id
        super().__init__(f"{resource_kind} {resource_id} was not found")


class CompetitionArchivedConflict(CoreResourceError):
    def __init__(self, competition_id: UUID) -> None:
        self.competition_id = competition_id
        self.message = "archived competitions cannot be changed"
        super().__init__(self.message)


class CompetitionSeasonYearExists(CoreResourceError):
    def __init__(self, competition_id: UUID, season_year: int) -> None:
        self.competition_id = competition_id
        self.season_year = season_year
        self.message = (
            f"competition {competition_id} already has season year {season_year}"
        )
        super().__init__(self.message)


class SleeperLeagueIdExists(CoreResourceError):
    def __init__(self, sleeper_league_id: str) -> None:
        self.sleeper_league_id = sleeper_league_id
        self.message = (
            f"Sleeper league ID {sleeper_league_id!r} is already attached to a season"
        )
        super().__init__(self.message)


class CompetitionConcurrencyConflict(CoreResourceError):
    def __init__(
        self,
        message: str,
        *,
        constraint_name: str | None = None,
    ) -> None:
        self.message = message
        self.constraint_name = constraint_name
        super().__init__(message)


class RosterMappingConflict(CoreResourceError):
    def __init__(self, message: str, *, stale_source: bool = False) -> None:
        self.message = message
        self.stale_source = stale_source
        super().__init__(message)


__all__ = [
    "CompetitionArchivedConflict",
    "CompetitionConcurrencyConflict",
    "CompetitionSeasonYearExists",
    "CoreResourceError",
    "CoreResourceNotFound",
    "RosterMappingConflict",
    "SleeperLeagueIdExists",
]
