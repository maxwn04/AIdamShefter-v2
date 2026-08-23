from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.reporting import Artifact, ArtifactVersion
from backend.database.models.reporting import Generation as StoredGeneration
from backend.database.models.sleeper import DataSnapshot, RefreshRun
from backend.database.sessions import SessionFactory
from backend.resources.core import (
    ArchiveCompetition,
    CompetitionManager,
    CompetitionOverviewReader,
    CompetitionQuery,
    CompetitionSeasonManager,
    CompetitionSeasonQuery,
    CoreResourceNotFound,
    CreateCompetition,
    CreateCompetitionSeason,
)
from backend.tests.resources.core.conftest import competition_context


def _season_manager(
    session_factory: SessionFactory,
    competition_id: UUID,
) -> CompetitionSeasonManager:
    return CompetitionSeasonManager(
        session_factory,
        competition_context(competition_id),
    )


def test_overview_pages_are_ordered_paginated_and_archive_aware(
    session_factory: SessionFactory,
    competition_manager: CompetitionManager,
) -> None:
    zulu = competition_manager.create(CreateCompetition(display_name="Zulu"))
    alpha = competition_manager.create(CreateCompetition(display_name="alpha"))
    archived = competition_manager.create(
        CreateCompetition(display_name="Archived")
    )
    latest = _season_manager(session_factory, alpha.id).create(
        CreateCompetitionSeason(
            season_year=2026,
            sleeper_league_id=f"league-{uuid4()}",
        )
    )
    competition_manager.archive(ArchiveCompetition(competition_id=archived.id))
    reader = CompetitionOverviewReader(session_factory)

    active = reader.list_competitions(CompetitionQuery(limit=1))
    next_page = reader.list_competitions(CompetitionQuery(limit=1, offset=1))
    all_rows = reader.list_competitions(
        CompetitionQuery(include_archived=True, limit=10)
    )

    assert active.total == 2
    assert active.items[0].competition.id == alpha.id
    assert active.items[0].summary.season_count == 1
    assert active.items[0].summary.latest_season == latest
    assert next_page.items[0].competition.id == zulu.id
    assert all_rows.total == 3
    assert archived.id in {item.competition.id for item in all_rows.items}


def test_activity_summaries_filter_status_and_use_deterministic_ties(
    database_engine: Engine,
    session_factory: SessionFactory,
    competition_manager: CompetitionManager,
) -> None:
    competition = competition_manager.create(
        CreateCompetition(display_name="Activity")
    )
    season = _season_manager(session_factory, competition.id).create(
        CreateCompetitionSeason(
            season_year=2026,
            sleeper_league_id=f"league-{uuid4()}",
        )
    )
    other = competition_manager.create(CreateCompetition(display_name="Other"))
    other_season = _season_manager(session_factory, other.id).create(
        CreateCompetitionSeason(
            season_year=2026,
            sleeper_league_id=f"league-{uuid4()}",
        )
    )
    base = datetime(2026, 8, 20, 12, tzinfo=UTC)
    successful_id = UUID(int=1)
    tied_failed_id = UUID(int=2)
    tied_partial_id = UUID(int=3)
    snapshot_id = uuid4()
    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(RefreshRun),
            [
                {
                    "id": successful_id,
                    "competition_id": competition.id,
                    "competition_season_id": season.id,
                    "requested_through_week": 7,
                    "endpoint_scope": {},
                    "trigger_source": "manual",
                    "status": "succeeded",
                    "code_version": "test",
                    "normalizer_version": "test",
                    "started_at": base,
                    "completed_at": base,
                    "request_count": 4,
                    "succeeded_request_count": 4,
                    "failed_request_count": 0,
                },
                {
                    "id": tied_failed_id,
                    "competition_id": competition.id,
                    "competition_season_id": season.id,
                    "requested_through_week": 8,
                    "endpoint_scope": {},
                    "trigger_source": "manual",
                    "status": "failed",
                    "code_version": "test",
                    "normalizer_version": "test",
                    "started_at": base + timedelta(days=1),
                    "completed_at": base + timedelta(days=1),
                    "request_count": 4,
                    "succeeded_request_count": 0,
                    "failed_request_count": 4,
                },
                {
                    "id": tied_partial_id,
                    "competition_id": competition.id,
                    "competition_season_id": season.id,
                    "requested_through_week": 9,
                    "endpoint_scope": {},
                    "trigger_source": "manual",
                    "status": "partial",
                    "code_version": "test",
                    "normalizer_version": "test",
                    "started_at": base + timedelta(days=1),
                    "completed_at": base + timedelta(days=1),
                    "request_count": 5,
                    "succeeded_request_count": 4,
                    "failed_request_count": 1,
                },
                {
                    "id": uuid4(),
                    "competition_id": competition.id,
                    "competition_season_id": season.id,
                    "requested_through_week": 10,
                    "endpoint_scope": {},
                    "trigger_source": "manual",
                    "status": "running",
                    "code_version": "test",
                    "normalizer_version": "test",
                    "started_at": base + timedelta(days=2),
                    "request_count": 0,
                    "succeeded_request_count": 0,
                    "failed_request_count": 0,
                },
            ],
        )
        connection.execute(
            sa.insert(DataSnapshot),
            [
                {
                    "id": snapshot_id,
                    "competition_id": competition.id,
                    "primary_competition_season_id": season.id,
                    "build_key": "a" * 64,
                    "domain_cutoff_week": 9,
                    "as_of_date": date(2026, 8, 21),
                    "status": "ready",
                    "snapshot_projection_version": "1",
                    "code_version": "test",
                    "completeness_warnings": [],
                    "sqlite_artifact_sha256": "b" * 64,
                    "sqlite_artifact_byte_length": 10,
                    "sqlite_artifact_storage_key": "snapshots/activity.sqlite",
                    "created_at": base,
                    "completed_at": base + timedelta(days=2),
                },
                {
                    "id": uuid4(),
                    "competition_id": competition.id,
                    "primary_competition_season_id": season.id,
                    "build_key": "c" * 64,
                    "domain_cutoff_week": 10,
                    "as_of_date": date(2026, 8, 22),
                    "status": "failed",
                    "snapshot_projection_version": "1",
                    "code_version": "test",
                    "completeness_warnings": [],
                    "failure_summary": {
                        "code": "failed",
                        "summary": "not ready",
                    },
                    "created_at": base,
                    "completed_at": base + timedelta(days=3),
                },
            ],
        )
        _insert_submitted_generation(
            connection,
            competition.id,
            season.id,
            completed_at=base + timedelta(days=4),
        )
        _insert_unsubmitted_generation(
            connection,
            competition.id,
            season.id,
            completed_at=base + timedelta(days=5),
        )
        connection.execute(
            sa.insert(RefreshRun),
            {
                "id": uuid4(),
                "competition_id": other.id,
                "competition_season_id": other_season.id,
                "requested_through_week": 18,
                "endpoint_scope": {},
                "trigger_source": "manual",
                "status": "succeeded",
                "code_version": "test",
                "normalizer_version": "test",
                "started_at": base + timedelta(days=10),
                "completed_at": base + timedelta(days=10),
                "request_count": 1,
                "succeeded_request_count": 1,
                "failed_request_count": 0,
            },
        )

    reader = CompetitionOverviewReader(session_factory)
    overview = reader.get_competition(competition.id)
    season_item = reader.list_seasons(
        competition.id, CompetitionSeasonQuery()
    ).items[0]

    assert overview.summary.latest_terminal_refresh is not None
    assert overview.summary.latest_terminal_refresh.status.value == "partial"
    assert overview.summary.latest_terminal_refresh.requested_through_week == 9
    assert overview.summary.latest_successful_refresh_at == base
    assert overview.summary.latest_ready_snapshot_at == base + timedelta(days=2)
    assert overview.summary.latest_submitted_article_at == base + timedelta(days=4)
    assert season_item.summary.latest_terminal_refresh is not None
    assert season_item.summary.latest_terminal_refresh.failed_request_count == 1
    assert season_item.summary.league_name is None


def test_season_detail_masks_cross_competition_and_allows_missing_normalized_data(
    session_factory: SessionFactory,
    competition_manager: CompetitionManager,
) -> None:
    first = competition_manager.create(CreateCompetition(display_name="First"))
    second = competition_manager.create(CreateCompetition(display_name="Second"))
    season = _season_manager(session_factory, first.id).create(
        CreateCompetitionSeason(
            season_year=2026,
            sleeper_league_id=f"league-{uuid4()}",
        )
    )
    reader = CompetitionOverviewReader(session_factory)

    detail = reader.get_season(first.id, season.id)
    assert detail.normalized_overview is None
    with pytest.raises(CoreResourceNotFound, match="competition_season"):
        reader.get_season(second.id, season.id)


def _insert_submitted_generation(
    connection: sa.Connection,
    competition_id: UUID,
    season_id: UUID,
    *,
    completed_at: datetime,
) -> None:
    generation_id = uuid4()
    artifact_id = uuid4()
    version_id = uuid4()
    connection.execute(
        sa.insert(StoredGeneration),
        {
            "id": generation_id,
            "competition_id": competition_id,
            "competition_season_id": season_id,
            "kind": "live",
            "status": "pending",
            "request_text": "recap",
            "requested_primary_model": "test-model",
            "settings_jsonb": {"schema_version": 1},
            "current_turn": 0,
        },
    )
    connection.execute(
        sa.insert(Artifact),
        {
            "id": artifact_id,
            "generation_id": generation_id,
            "path": "article.md",
            "media_type": "text/markdown",
        },
    )
    connection.execute(
        sa.insert(ArtifactVersion),
        {
            "id": version_id,
            "artifact_id": artifact_id,
            "generation_id": generation_id,
            "revision_number": 1,
            "content": "# Article",
            "content_hash": "d" * 64,
        },
    )
    connection.execute(
        sa.update(Artifact)
        .where(Artifact.id == artifact_id)
        .values(finalized_version_id=version_id, finalized_at=completed_at)
    )
    connection.execute(
        sa.update(StoredGeneration)
        .where(StoredGeneration.id == generation_id)
        .values(
            status="succeeded",
            submitted_artifact_version_id=version_id,
            completed_at=completed_at,
        )
    )


def _insert_unsubmitted_generation(
    connection: sa.Connection,
    competition_id: UUID,
    season_id: UUID,
    *,
    completed_at: datetime,
) -> None:
    connection.execute(
        sa.insert(StoredGeneration),
        {
            "id": uuid4(),
            "competition_id": competition_id,
            "competition_season_id": season_id,
            "kind": "live",
            "status": "succeeded",
            "request_text": "draft only",
            "requested_primary_model": "test-model",
            "settings_jsonb": {"schema_version": 1},
            "current_turn": 1,
            "completed_at": completed_at,
        },
    )
