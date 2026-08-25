from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.api.app import create_app
from backend.api.dependencies.competitions import (
    get_competition_catalog_dependencies,
    get_competition_season_dependencies,
)
from backend.composition import ApiRuntimeDependencies
from backend.resources.core import (
    Competition,
    CompetitionActivitySummary,
    CompetitionArchivedConflict,
    CompetitionConcurrencyConflict,
    CompetitionOverview,
    CompetitionOverviewPage,
    CompetitionQuery,
    CompetitionSeason,
    CompetitionSeasonActivitySummary,
    CompetitionSeasonDetail,
    CompetitionSeasonOverview,
    CompetitionSeasonOverviewPage,
    CompetitionSeasonQuery,
    CompetitionSeasonYearExists,
    CoreResourceNotFound,
    SleeperLeagueIdExists,
)


NOW = datetime(2026, 8, 23, 12, tzinfo=UTC)


class StubRuntime:
    def assert_ready(self) -> None:
        pass

    def close(self) -> None:
        pass


def runtime_factory() -> ApiRuntimeDependencies:
    return StubRuntime()


class StubCompetitionManager:
    def __init__(self, competition: Competition) -> None:
        self.competition = competition
        self.created: list[object] = []
        self.renamed: list[object] = []
        self.archived: list[object] = []
        self.error: Exception | None = None

    def create(self, command: object) -> Competition:
        self.created.append(command)
        self._raise()
        return self.competition

    def rename(self, command: object) -> Competition:
        self.renamed.append(command)
        self._raise()
        return self.competition.model_copy(update={"display_name": "Renamed"})

    def archive(self, command: object) -> Competition:
        self.archived.append(command)
        self._raise()
        return self.competition.model_copy(update={"archived_at": NOW})

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error


class StubSeasonManager:
    def __init__(self, season: CompetitionSeason) -> None:
        self.season = season
        self.created: list[object] = []
        self.error: Exception | None = None

    def create(self, command: object) -> CompetitionSeason:
        self.created.append(command)
        if self.error is not None:
            raise self.error
        return self.season


class StubOverviewReader:
    def __init__(
        self,
        overview: CompetitionOverview,
        season_overview: CompetitionSeasonOverview,
        season_detail: CompetitionSeasonDetail,
    ) -> None:
        self.overview = overview
        self.season_overview = season_overview
        self.season_detail = season_detail
        self.competition_queries: list[CompetitionQuery] = []
        self.season_queries: list[tuple[UUID, CompetitionSeasonQuery]] = []
        self.competition_ids: list[UUID] = []
        self.season_ids: list[tuple[UUID, UUID]] = []
        self.error: Exception | None = None

    def list_competitions(self, query: CompetitionQuery) -> CompetitionOverviewPage:
        self.competition_queries.append(query)
        self._raise()
        return CompetitionOverviewPage(
            items=(self.overview,), total=1, limit=query.limit, offset=query.offset
        )

    def get_competition(self, competition_id: UUID) -> CompetitionOverview:
        self.competition_ids.append(competition_id)
        self._raise()
        return self.overview

    def list_seasons(
        self,
        competition_id: UUID,
        query: CompetitionSeasonQuery,
    ) -> CompetitionSeasonOverviewPage:
        self.season_queries.append((competition_id, query))
        self._raise()
        return CompetitionSeasonOverviewPage(
            items=(self.season_overview,),
            total=1,
            limit=query.limit,
            offset=query.offset,
        )

    def get_season(
        self,
        competition_id: UUID,
        season_id: UUID,
    ) -> CompetitionSeasonDetail:
        self.season_ids.append((competition_id, season_id))
        self._raise()
        return self.season_detail

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error


def _dependencies() -> SimpleNamespace:
    competition_id = uuid4()
    season_id = uuid4()
    competition = Competition(
        id=competition_id,
        display_name="The League",
        created_at=NOW,
        updated_at=NOW,
        archived_at=None,
    )
    season = CompetitionSeason(
        id=season_id,
        competition_id=competition_id,
        season_year=2026,
        sequence_number=1,
        sleeper_league_id="sleeper-2026",
        created_at=NOW,
    )
    season_summary = CompetitionSeasonActivitySummary(
        league_name=None,
        league_status=None,
        latest_terminal_refresh=None,
        latest_successful_refresh_at=None,
        latest_ready_snapshot_at=None,
    )
    season_overview = CompetitionSeasonOverview(
        season=season,
        summary=season_summary,
    )
    overview = CompetitionOverview(
        competition=competition,
        summary=CompetitionActivitySummary(
            season_count=1,
            latest_season=season,
            latest_terminal_refresh=None,
            latest_successful_refresh_at=None,
            latest_ready_snapshot_at=None,
            latest_submitted_article_at=None,
        ),
    )
    reader = StubOverviewReader(
        overview,
        season_overview,
        CompetitionSeasonDetail(
            season=season,
            summary=season_summary,
            normalized_overview=None,
        ),
    )
    return SimpleNamespace(
        competition=competition,
        season=season,
        competitions=StubCompetitionManager(competition),
        seasons=StubSeasonManager(season),
        overviews=reader,
    )


async def _client(dependencies: SimpleNamespace) -> tuple[Any, AsyncClient]:
    app = create_app(runtime_factory=runtime_factory)
    app.dependency_overrides[get_competition_catalog_dependencies] = lambda: (
        dependencies
    )
    app.dependency_overrides[get_competition_season_dependencies] = lambda: (
        dependencies
    )
    return app, AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    )


@pytest.mark.asyncio
async def test_competition_catalog_routes_preserve_contracts() -> None:
    dependencies = _dependencies()
    app, client = await _client(dependencies)
    base = "/api/v1/competitions"

    async with app.router.lifespan_context(app), client:
        listed = await client.get(
            f"{base}?include_archived=true&limit=12&offset=3"
        )
        created = await client.post(base, json={"display_name": " The League "})
        detail = await client.get(f"{base}/{dependencies.competition.id}")
        renamed = await client.patch(
            f"{base}/{dependencies.competition.id}",
            json={"display_name": " Renamed "},
        )
        archived = await client.patch(
            f"{base}/{dependencies.competition.id}",
            json={"archived": True},
        )
        archived_again = await client.patch(
            f"{base}/{dependencies.competition.id}",
            json={"archived": True},
        )

    assert listed.status_code == 200
    assert listed.json()["page"]["items"][0]["summary"]["season_count"] == 1
    assert dependencies.overviews.competition_queries == [
        CompetitionQuery(include_archived=True, limit=12, offset=3)
    ]
    assert created.status_code == 201
    assert dependencies.competitions.created[0].display_name == "The League"
    assert detail.json()["competition"]["id"] == str(dependencies.competition.id)
    assert renamed.json()["competition"]["display_name"] == "Renamed"
    assert dependencies.competitions.renamed[0].display_name == "Renamed"
    assert archived.json()["competition"]["archived_at"] is not None
    assert archived_again.status_code == 200
    assert dependencies.competitions.archived[0].competition_id == (
        dependencies.competition.id
    )


@pytest.mark.asyncio
async def test_competition_season_routes_are_scoped_and_ordered() -> None:
    dependencies = _dependencies()
    app, client = await _client(dependencies)
    base = f"/api/v1/competitions/{dependencies.competition.id}/seasons"

    async with app.router.lifespan_context(app), client:
        listed = await client.get(f"{base}?limit=7&offset=2")
        created = await client.post(
            base,
            json={
                "season_year": 2026,
                "sleeper_league_id": " sleeper-2026 ",
            },
        )
        detail = await client.get(f"{base}/{dependencies.season.id}")

    assert listed.status_code == 200
    assert dependencies.overviews.season_queries == [
        (
            dependencies.competition.id,
            CompetitionSeasonQuery(limit=7, offset=2),
        )
    ]
    assert created.status_code == 201
    assert dependencies.seasons.created[0].sleeper_league_id == "sleeper-2026"
    assert detail.status_code == 200
    assert detail.json()["normalized_overview"] is None
    assert dependencies.overviews.season_ids == [
        (dependencies.competition.id, dependencies.season.id)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"display_name": None},
        {"archived": False},
        {"display_name": "Renamed", "archived": True},
        {"unknown": "value"},
    ],
)
async def test_competition_patch_rejects_ambiguous_bodies(
    payload: dict[str, object],
) -> None:
    dependencies = _dependencies()
    app, client = await _client(dependencies)

    async with app.router.lifespan_context(app), client:
        response = await client.patch(
            f"/api/v1/competitions/{dependencies.competition.id}",
            json=payload,
        )

    assert response.status_code == 422
    assert dependencies.competitions.renamed == []
    assert dependencies.competitions.archived == []


@pytest.mark.asyncio
async def test_typed_core_errors_have_stable_safe_payloads() -> None:
    dependencies = _dependencies()
    app, client = await _client(dependencies)
    base = f"/api/v1/competitions/{dependencies.competition.id}"

    async with app.router.lifespan_context(app), client:
        dependencies.overviews.error = CoreResourceNotFound(
            "competition", dependencies.competition.id
        )
        missing_competition = await client.get(base)
        dependencies.overviews.error = CoreResourceNotFound(
            "competition_season", dependencies.season.id
        )
        missing = await client.get(f"{base}/seasons/{dependencies.season.id}")
        dependencies.overviews.error = None
        dependencies.seasons.error = CompetitionSeasonYearExists(
            dependencies.competition.id, 2026
        )
        duplicate = await client.post(
            f"{base}/seasons",
            json={"season_year": 2026, "sleeper_league_id": "different"},
            headers={"X-Correlation-ID": str(uuid4())},
        )
        dependencies.seasons.error = SleeperLeagueIdExists("different")
        duplicate_league = await client.post(
            f"{base}/seasons",
            json={"season_year": 2027, "sleeper_league_id": "different"},
        )
        dependencies.seasons.error = CompetitionArchivedConflict(
            dependencies.competition.id
        )
        archived = await client.post(
            f"{base}/seasons",
            json={"season_year": 2027, "sleeper_league_id": "new"},
        )
        dependencies.competitions.error = CompetitionConcurrencyConflict(
            "unsafe database detail", constraint_name="secret_constraint"
        )
        concurrent = await client.post(
            "/api/v1/competitions", json={"display_name": "Concurrent"}
        )

    assert missing_competition.status_code == 404
    assert missing_competition.json()["error"]["code"] == "competition_not_found"
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "competition_season_not_found",
            "summary": "competition season was not found",
        }
    }
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "competition_season_year_exists"
    assert duplicate.json()["error"]["field_errors"] == {
        "season_year": ["Already attached to this competition."]
    }
    assert "constraint" not in duplicate.text
    assert duplicate_league.status_code == 409
    assert duplicate_league.json()["error"]["code"] == "sleeper_league_id_exists"
    assert duplicate_league.json()["error"]["field_errors"] == {
        "sleeper_league_id": ["Already attached to another season."]
    }
    assert archived.status_code == 409
    assert archived.json()["error"]["code"] == "competition_archived"
    assert concurrent.status_code == 409
    assert concurrent.json()["error"]["code"] == (
        "competition_concurrency_conflict"
    )
    assert "secret_constraint" not in concurrent.text
    assert "unsafe database detail" not in concurrent.text


def test_openapi_contains_competition_and_season_boundaries() -> None:
    schema = create_app(runtime_factory=runtime_factory).openapi()
    paths = set(schema["paths"])
    base = "/api/v1/competitions"

    assert {
        base,
        f"{base}/{{competition_id}}",
        f"{base}/{{competition_id}}/seasons",
        f"{base}/{{competition_id}}/seasons/{{season_id}}",
    }.issubset(paths)
    patch_schema = schema["paths"][f"{base}/{{competition_id}}"]["patch"]
    assert "422" in patch_schema["responses"]
    assert "409" in patch_schema["responses"]
    assert patch_schema["responses"]["409"]["content"]["application/json"][
        "example"
    ]["error"]["code"] == "competition_season_year_exists"
