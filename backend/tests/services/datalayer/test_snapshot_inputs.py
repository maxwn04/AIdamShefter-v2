from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.resources.core import SeasonRosterIdentity
from backend.resources.sleeper_data.league_seasons import (
    SnapshotLineage,
    SnapshotSeasonIdentity,
)
from backend.resources.sleeper_data.refreshes import RefreshNeedReason
from backend.resources.sleeper_data.requests import (
    ApiRequestCandidate,
    InlineVerifiedPayload,
    LatestCompleteCandidatesQuery,
)
from backend.services.datalayer.canonical_json import (
    canonical_json_bytes,
    canonical_json_sha256,
)
from backend.services.datalayer.contracts import SnapshotRequest
from backend.services.datalayer.snapshot_inputs import (
    MapSeasonRosters,
    PrepareSnapshotRequest,
    RefreshSeason,
    ResolvedSnapshotInputs,
    SnapshotInputResolver,
    SnapshotPreparationMode,
)
from backend.services.datalayer.sleeper.scope import EndpointKind, ScopeKey


NOW = datetime(2026, 8, 25, 20, 0, tzinfo=timezone.utc)
COMPETITION_ID = UUID("20000000-0000-0000-0000-000000000001")
HISTORY_ID = UUID("10000000-0000-0000-0000-000000000001")
PRIMARY_ID = UUID("10000000-0000-0000-0000-000000000002")


def _identity(season_id: UUID, year: int, sequence: int) -> SnapshotSeasonIdentity:
    return SnapshotSeasonIdentity(
        competition_id=COMPETITION_ID,
        competition_season_id=season_id,
        sleeper_league_id=f"league-{year}",
        season_year=year,
        sequence_number=sequence,
    )


def _lineage(*, primary_is_latest: bool = True) -> SnapshotLineage:
    return SnapshotLineage(
        primary_competition_season_id=PRIMARY_ID,
        primary_is_latest=primary_is_latest,
        seasons=(
            _identity(HISTORY_ID, 2025, 1),
            _identity(PRIMARY_ID, 2026, 2),
        ),
    )


def _prepare(mode: SnapshotPreparationMode = SnapshotPreparationMode.LIVE):
    return PrepareSnapshotRequest(
        snapshot=SnapshotRequest(
            competition_season_id=PRIMARY_ID,
            through_week=3,
            as_of_date=date(2026, 8, 25),
        ),
        mode=mode,
        requested_at=NOW,
    )


class _LineageReader:
    def __init__(self, lineage: SnapshotLineage):
        self.lineage = lineage

    def get_snapshot_lineage(self, season_id: UUID) -> SnapshotLineage:
        assert season_id == PRIMARY_ID
        return self.lineage


class _Files:
    pass


class _Mappings:
    def __init__(
        self,
        *,
        mapped_seasons: set[UUID] | None = None,
        franchise_salt: str = "base",
    ) -> None:
        self.mapped_seasons = (
            {HISTORY_ID, PRIMARY_ID}
            if mapped_seasons is None
            else mapped_seasons
        )
        self.franchise_salt = franchise_salt
        self.calls: list[tuple[UUID, ...]] = []

    def list_snapshot_mappings(
        self,
        season_ids: list[UUID],
    ) -> tuple[SeasonRosterIdentity, ...]:
        self.calls.append(tuple(season_ids))
        return tuple(
            SeasonRosterIdentity(
                id=uuid5(NAMESPACE_URL, f"roster:{season_id}:1"),
                competition_season_id=season_id,
                franchise_id=uuid5(
                    NAMESPACE_URL,
                    f"franchise:{self.franchise_salt}:{season_id}",
                ),
                sleeper_roster_id="1",
            )
            for season_id in season_ids
            if season_id in self.mapped_seasons
        )


class _Candidates:
    def __init__(
        self,
        *,
        missing: set[ScopeKey] | None = None,
        id_salt: str = "base",
        payload_salt: str = "base",
        completion_offset: timedelta = timedelta(),
        completed_by_season: dict[UUID, datetime] | None = None,
        history_draft_rounds: int = 0,
    ) -> None:
        self.missing = missing or set()
        self.id_salt = id_salt
        self.payload_salt = payload_salt
        self.completion_offset = completion_offset
        self.completed_by_season = completed_by_season or {}
        self.history_draft_rounds = history_draft_rounds
        self.queries: list[tuple[ScopeKey, ...]] = []
        self._candidates: dict[UUID, ApiRequestCandidate] = {}
        self._payloads: dict[UUID, InlineVerifiedPayload] = {}

    def list_latest_complete_candidates(
        self,
        query: LatestCompleteCandidatesQuery,
    ) -> tuple[ApiRequestCandidate, ...]:
        self.queries.append(query.scope_keys)
        return tuple(
            self._candidate(scope)
            for scope in query.scope_keys
            if scope not in self.missing
        )

    def resolve_verified_payloads(
        self,
        request_ids: list[UUID],
    ) -> tuple[InlineVerifiedPayload, ...]:
        return tuple(self._payloads[request_id] for request_id in request_ids)

    def _candidate(self, scope: ScopeKey) -> ApiRequestCandidate:
        request_id = uuid5(NAMESPACE_URL, f"{self.id_salt}:{scope.value}")
        existing = self._candidates.get(request_id)
        if existing is not None:
            return existing
        parts = scope.value.split(":")
        kind = EndpointKind(parts[0])
        season_id = None if kind is EndpointKind.PLAYER_CATALOG else UUID(parts[1])
        payload = self._payload(kind, season_id)
        sha256 = canonical_json_sha256(payload)
        completed_at = (
            self.completed_by_season.get(season_id, NOW)
            + self.completion_offset
        )
        candidate = ApiRequestCandidate(
            request_id=request_id,
            competition_season_id=season_id,
            endpoint_kind=kind,
            scope_key=scope,
            week=(int(parts[2]) if kind in _WEEKLY else None),
            bracket_kind=(parts[2] if kind in _BRACKETS else None),
            requested_at=completed_at - timedelta(seconds=1),
            completed_at=completed_at,
            payload_id=uuid5(NAMESPACE_URL, f"payload:{request_id}"),
            response_sha256=sha256,
        )
        self._candidates[request_id] = candidate
        self._payloads[request_id] = InlineVerifiedPayload(
            request_id=request_id,
            scope_key=scope,
            sha256=sha256,
            byte_length=len(canonical_json_bytes(payload)),
            media_type="application/json",
            payload=payload,
        )
        return candidate

    def _payload(self, kind: EndpointKind, season_id: UUID | None) -> Any:
        if kind is EndpointKind.LEAGUE:
            assert season_id is not None
            year = 2025 if season_id == HISTORY_ID else 2026
            return {
                "league_id": f"league-{year}",
                "name": f"League {year}",
                "season": str(year),
                "sport": "nfl",
                "settings": {
                    "draft_rounds": (
                        self.history_draft_rounds if season_id == HISTORY_ID else 0
                    ),
                    "league_average_match": 0,
                    "playoff_teams": 6,
                    "playoff_week_start": 15,
                },
                "scoring_settings": {},
                "roster_positions": ["QB"],
                "test_payload_revision": self.payload_salt,
            }
        if kind is EndpointKind.LEAGUE_ROSTERS:
            return [
                {
                    "roster_id": 1,
                    "owner_id": "owner",
                    "players": [],
                    "starters": [],
                    "settings": {},
                    "metadata": {},
                }
            ]
        return []


_WEEKLY = {EndpointKind.MATCHUPS, EndpointKind.TRANSACTIONS}
_BRACKETS = {EndpointKind.WINNERS_BRACKET, EndpointKind.LOSERS_BRACKET}


def _resolve(
    candidates: _Candidates,
    *,
    mappings: _Mappings | None = None,
    lineage: SnapshotLineage | None = None,
    mode: SnapshotPreparationMode = SnapshotPreparationMode.READINESS_ONLY,
):
    mapping_reader = mappings or _Mappings()
    state = SnapshotInputResolver(
        lineage=_LineageReader(lineage or _lineage()),
        requests=candidates,
        mappings=mapping_reader,
        files=_Files(),  # type: ignore[arg-type]
    ).resolve(_prepare(mode))
    return state, mapping_reader


def test_resolves_all_predecessors_from_raw_league_settings_in_two_batches() -> None:
    candidates = _Candidates(history_draft_rounds=3)

    state, mappings = _resolve(candidates)

    assert isinstance(state, ResolvedSnapshotInputs)
    assert [(season.identity.season_year, season.through_week) for season in state.seasons] == [
        (2025, 18),
        (2026, 3),
    ]
    assert any(
        scope.value == f"traded_picks:{HISTORY_ID}"
        for scope in state.requirements.scope_keys
    )
    assert all(
        not scope.value.startswith("nfl_state:")
        for scope in state.requirements.scope_keys
    )
    assert len(candidates.queries) == 2
    assert len(candidates.queries[0]) == 2
    assert mappings.calls == [(HISTORY_ID, PRIMARY_ID)]


def test_missing_inputs_choose_oldest_season_and_global_catalog_targets_primary() -> None:
    history_users = ScopeKey.from_parts(EndpointKind.LEAGUE_USERS, HISTORY_ID)
    primary_users = ScopeKey.from_parts(EndpointKind.LEAGUE_USERS, PRIMARY_ID)
    state, _ = _resolve(_Candidates(missing={history_users, primary_users}))

    assert isinstance(state, RefreshSeason)
    assert state.season.competition_season_id == HISTORY_ID
    assert state.missing_scopes == (history_users,)

    player_scope = ScopeKey.from_parts(EndpointKind.PLAYER_CATALOG, "nfl")
    state, _ = _resolve(_Candidates(missing={player_scope}))
    assert isinstance(state, RefreshSeason)
    assert state.season.competition_season_id == PRIMARY_ID
    assert state.missing_scopes == (player_scope,)


def test_only_latest_live_primary_applies_strict_age_boundary() -> None:
    completed = {
        HISTORY_ID: NOW - timedelta(days=1000),
        PRIMARY_ID: NOW - timedelta(seconds=900),
    }
    state, _ = _resolve(
        _Candidates(completed_by_season=completed),
        mode=SnapshotPreparationMode.LIVE,
    )
    assert isinstance(state, ResolvedSnapshotInputs)

    completed[PRIMARY_ID] = NOW - timedelta(seconds=901)
    state, _ = _resolve(
        _Candidates(completed_by_season=completed),
        mode=SnapshotPreparationMode.LIVE,
    )
    assert isinstance(state, RefreshSeason)
    assert state.season.competition_season_id == PRIMARY_ID
    assert state.reason is RefreshNeedReason.STALE

    state, _ = _resolve(
        _Candidates(completed_by_season=completed),
        lineage=_lineage(primary_is_latest=False),
        mode=SnapshotPreparationMode.LIVE,
    )
    assert isinstance(state, ResolvedSnapshotInputs)


def test_mapping_bootstrap_and_later_season_mapping_state_are_distinct() -> None:
    state, _ = _resolve(_Candidates(), mappings=_Mappings(mapped_seasons=set()))
    assert isinstance(state, RefreshSeason)
    assert state.season.competition_season_id == HISTORY_ID

    state, _ = _resolve(
        _Candidates(),
        mappings=_Mappings(mapped_seasons={HISTORY_ID}),
    )
    assert isinstance(state, MapSeasonRosters)
    assert state.season.competition_season_id == PRIMARY_ID
    assert state.roster_ids == ("1",)


def test_revision_ignores_request_audit_identity_but_tracks_facts_and_mappings() -> None:
    first, _ = _resolve(_Candidates(id_salt="first"))
    audit_changed, _ = _resolve(
        _Candidates(id_salt="second", completion_offset=timedelta(hours=-1))
    )
    payload_changed, _ = _resolve(_Candidates(payload_salt="changed"))
    mapping_changed, _ = _resolve(
        _Candidates(),
        mappings=_Mappings(franchise_salt="changed"),
    )

    assert isinstance(first, ResolvedSnapshotInputs)
    assert isinstance(audit_changed, ResolvedSnapshotInputs)
    assert isinstance(payload_changed, ResolvedSnapshotInputs)
    assert isinstance(mapping_changed, ResolvedSnapshotInputs)
    assert first.input_revision == audit_changed.input_revision
    assert first.input_revision != payload_changed.input_revision
    assert first.input_revision != mapping_changed.input_revision
