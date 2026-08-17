from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.core import Competition, CompetitionSeason, Franchise
from backend.database.models.memory import (
    CurrentRevision,
    EventVersion,
    FactVersion,
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
    StorylineVersion,
)
from backend.database.models.reporting import Generation
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common import (
    CrossCompetitionReferenceError,
    StaleItemVersionError,
    TargetNotFoundError,
    WrongTargetKindError,
)
from backend.resources.memory.revisions.writers import persist_version_envelopes
from backend.resources.memory.search_documents import (
    STORYLINE_DOCUMENT_BUILDER_VERSION,
)
from backend.resources.memory.storylines import StorylineContent, StorylineManager
from backend.resources.memory.storylines.shared import (
    insert_storyline_version,
    prepare_storyline_replacement,
    prepare_storyline_write,
)
from backend.tests.database.conftest import database_engine, migrated_database


@dataclass(frozen=True)
class StorylineDomain:
    competition_id: UUID
    other_competition_id: UUID
    season_id: UUID
    generation_id: UUID
    franchise_id: UUID
    root_revision_id: UUID
    current_revision_id: UUID
    historical_fact_version_id: UUID
    current_fact_version_id: UUID
    event_item_id: UUID
    event_version_id: UUID
    related_storyline_item_id: UUID
    related_storyline_version_id: UUID
    cross_storyline_item_id: UUID
    cross_storyline_version_id: UUID


def _seed_domain(database_engine: Engine) -> StorylineDomain:
    competition_id = uuid4()
    other_competition_id = uuid4()
    season_id = uuid4()
    other_season_id = uuid4()
    generation_id = uuid4()
    other_generation_id = uuid4()
    franchise_id = uuid4()
    root_revision_id = uuid4()
    current_revision_id = uuid4()
    other_revision_id = uuid4()
    fact_item_id = uuid4()
    historical_fact_version_id = uuid4()
    current_fact_version_id = uuid4()
    event_item_id = uuid4()
    event_version_id = uuid4()
    related_storyline_item_id = uuid4()
    related_storyline_version_id = uuid4()
    cross_storyline_item_id = uuid4()
    cross_storyline_version_id = uuid4()

    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            [
                {"id": competition_id, "display_name": "Storyline League"},
                {"id": other_competition_id, "display_name": "Other League"},
            ],
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            [
                {
                    "id": season_id,
                    "competition_id": competition_id,
                    "season_year": 2026,
                    "sequence_number": 1,
                    "sleeper_league_id": f"league-{uuid4()}",
                },
                {
                    "id": other_season_id,
                    "competition_id": other_competition_id,
                    "season_year": 2026,
                    "sequence_number": 1,
                    "sleeper_league_id": f"league-{uuid4()}",
                },
            ],
        )
        connection.execute(
            sa.insert(Franchise),
            {
                "id": franchise_id,
                "competition_id": competition_id,
                "display_name": "Sharks",
            },
        )
        connection.execute(
            sa.insert(Generation),
            [
                _generation(generation_id, competition_id, season_id),
                _generation(
                    other_generation_id,
                    other_competition_id,
                    other_season_id,
                ),
            ],
        )
        connection.execute(
            sa.insert(MemoryRevision),
            [
                _revision(root_revision_id, competition_id, 0, season_id),
                _revision(
                    current_revision_id,
                    competition_id,
                    1,
                    season_id,
                    previous_revision_id=root_revision_id,
                ),
                _revision(
                    other_revision_id,
                    other_competition_id,
                    0,
                    other_season_id,
                ),
            ],
        )
        connection.execute(
            sa.insert(CurrentRevision),
            [
                {
                    "competition_id": competition_id,
                    "current_revision_id": current_revision_id,
                    "lock_version": 1,
                },
                {
                    "competition_id": other_competition_id,
                    "current_revision_id": other_revision_id,
                    "lock_version": 0,
                },
            ],
        )
        connection.execute(
            sa.insert(MemoryItem),
            [
                _item(fact_item_id, competition_id, "fact"),
                _item(event_item_id, competition_id, "event"),
                _item(related_storyline_item_id, competition_id, "storyline"),
                _item(
                    cross_storyline_item_id,
                    other_competition_id,
                    "storyline",
                ),
            ],
        )
        connection.execute(
            sa.insert(MemoryVersion),
            [
                _version(
                    historical_fact_version_id,
                    fact_item_id,
                    competition_id,
                    1,
                    root_revision_id,
                    season_id,
                    generation_id,
                    retired_revision_id=current_revision_id,
                ),
                _version(
                    current_fact_version_id,
                    fact_item_id,
                    competition_id,
                    2,
                    current_revision_id,
                    season_id,
                    generation_id,
                ),
                _version(
                    event_version_id,
                    event_item_id,
                    competition_id,
                    1,
                    root_revision_id,
                    season_id,
                    generation_id,
                ),
                _version(
                    related_storyline_version_id,
                    related_storyline_item_id,
                    competition_id,
                    1,
                    root_revision_id,
                    season_id,
                    generation_id,
                ),
                _version(
                    cross_storyline_version_id,
                    cross_storyline_item_id,
                    other_competition_id,
                    1,
                    other_revision_id,
                    other_season_id,
                    other_generation_id,
                ),
            ],
        )
        connection.execute(
            sa.insert(FactVersion),
            [
                _fact(historical_fact_version_id, competition_id, "superseded"),
                _fact(current_fact_version_id, competition_id, "active"),
            ],
        )
        connection.execute(
            sa.insert(EventVersion),
            {
                "version_id": event_version_id,
                "competition_id": competition_id,
                "event_type": "matchup",
                "headline": "The Owls beat the Sharks.",
                "summary": "The first rivalry meeting set the stakes.",
                "salience": 3,
                "confidence": "unverified",
                "status": "active",
                "details": {
                    "kind": "matchup",
                    "winner_franchise_id": str(uuid4()),
                    "loser_franchise_id": str(uuid4()),
                    "sleeper_matchup_id": "seed-matchup",
                },
            },
        )
        connection.execute(
            sa.insert(StorylineVersion),
            [
                _storyline_row(related_storyline_version_id),
                _storyline_row(cross_storyline_version_id),
            ],
        )

    return StorylineDomain(
        competition_id=competition_id,
        other_competition_id=other_competition_id,
        season_id=season_id,
        generation_id=generation_id,
        franchise_id=franchise_id,
        root_revision_id=root_revision_id,
        current_revision_id=current_revision_id,
        historical_fact_version_id=historical_fact_version_id,
        current_fact_version_id=current_fact_version_id,
        event_item_id=event_item_id,
        event_version_id=event_version_id,
        related_storyline_item_id=related_storyline_item_id,
        related_storyline_version_id=related_storyline_version_id,
        cross_storyline_item_id=cross_storyline_item_id,
        cross_storyline_version_id=cross_storyline_version_id,
    )


def _generation(
    generation_id: UUID,
    competition_id: UUID,
    season_id: UUID,
) -> dict[str, object]:
    return {
        "id": generation_id,
        "competition_id": competition_id,
        "competition_season_id": season_id,
        "kind": "test",
        "status": "pending",
        "request_text": "seed storyline manager",
        "requested_primary_model": "test-model",
        "settings_jsonb": {},
        "current_turn": 0,
    }


def _revision(
    revision_id: UUID,
    competition_id: UUID,
    sequence_number: int,
    season_id: UUID,
    *,
    previous_revision_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "id": revision_id,
        "competition_id": competition_id,
        "sequence_number": sequence_number,
        "previous_revision_id": previous_revision_id,
        "competition_season_id": season_id,
        "week": sequence_number,
        "state_content_hash": f"seed-{revision_id}",
    }


def _item(item_id: UUID, competition_id: UUID, kind: str) -> dict[str, object]:
    return {"id": item_id, "competition_id": competition_id, "kind": kind}


def _version(
    version_id: UUID,
    item_id: UUID,
    competition_id: UUID,
    revision_number: int,
    introduced_revision_id: UUID,
    season_id: UUID,
    generation_id: UUID,
    *,
    retired_revision_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "id": version_id,
        "item_id": item_id,
        "competition_id": competition_id,
        "revision_number": revision_number,
        "content_schema_version": 1,
        "introduced_revision_id": introduced_revision_id,
        "retired_revision_id": retired_revision_id,
        "competition_season_id": season_id,
        "week": revision_number,
        "creating_generation_id": generation_id,
    }


def _fact(
    version_id: UUID,
    competition_id: UUID,
    status: str,
) -> dict[str, object]:
    return {
        "version_id": version_id,
        "competition_id": competition_id,
        "claim": "The Sharks lost a rivalry meeting.",
        "category": "result",
        "structured_numbers": {"losses": 1},
        "confidence": "unverified",
        "subjects": [],
        "originating_event_version_ids": [],
        "status": status,
    }


def _storyline_row(version_id: UUID) -> dict[str, object]:
    return {
        "version_id": version_id,
        "headline": "A related arc",
        "summary": "Stable storyline relationship target.",
        "status": "active",
        "salience": 2,
        "tags": [],
        "subjects": [],
        "evidence": [],
        "related_storylines": [],
    }


def _content(
    domain: StorylineDomain,
    *,
    replacement: bool = False,
) -> StorylineContent:
    evidence: list[dict[str, object]] = [
        {
            "kind": "fact",
            "version_id": domain.historical_fact_version_id,
            "role": "support",
        }
    ]
    related: list[dict[str, object]] = []
    if not replacement:
        evidence.append(
            {
                "kind": "event",
                "version_id": domain.event_version_id,
                "role": "origin",
            }
        )
        related.append(
            {
                "item_id": domain.related_storyline_item_id,
                "role": "continuation",
            }
        )
    return StorylineContent.model_validate(
        {
            "headline": "The Sharks seek revenge" if not replacement else "Revenge paid",
            "summary": "A rivalry continues." if not replacement else "The arc closed.",
            "status": "active" if not replacement else "resolved",
            "arc_type": "rivalry",
            "salience": 5,
            "tags": ["Rivalry", "Playoffs"],
            "subjects": [
                {
                    "kind": "franchise",
                    "id": domain.franchise_id,
                    "role": "focus",
                    "display_name": "Sharks",
                }
            ],
            "evidence": evidence,
            "related_storylines": related,
            "callback_condition": None if replacement else "Revisit after rematch.",
            "resolution_summary": "The Sharks won." if replacement else None,
        }
    )


def _manager(database_engine: Engine, competition_id: UUID) -> StorylineManager:
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "local_user"},
            "scope": {"kind": "competition", "competition_id": competition_id},
            "correlation_id": uuid4(),
        }
    )
    return StorylineManager(create_session_factory(database_engine), context)


def test_storyline_lifecycle_preserves_exact_evidence_and_complete_replacement(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    session_factory = create_session_factory(database_engine)
    item_id = uuid4()
    first_version_id = uuid4()
    first_revision_id = uuid4()
    second_version_id = uuid4()
    second_revision_id = uuid4()

    with session_factory.begin() as session:
        revision = MemoryRevision(
            id=first_revision_id,
            competition_id=domain.competition_id,
            sequence_number=2,
            previous_revision_id=domain.current_revision_id,
            competition_season_id=domain.season_id,
            week=3,
            state_content_hash="storyline-state-one",
        )
        item = MemoryItem(
            id=item_id,
            competition_id=domain.competition_id,
            kind="storyline",
        )
        version = MemoryVersion(
            id=first_version_id,
            item_id=item_id,
            competition_id=domain.competition_id,
            revision_number=1,
            content_schema_version=1,
            introduced_revision_id=first_revision_id,
            competition_season_id=domain.season_id,
            week=3,
            creating_generation_id=domain.generation_id,
        )
        persist_version_envelopes(
            session,
            revision,
            new_items=(item,),
            new_versions=(version,),
        )
        prepared = prepare_storyline_write(
            session,
            domain.competition_id,
            _content(domain),
        )
        insert_storyline_version(session, version, prepared)
        session.execute(
            sa.update(CurrentRevision)
            .where(CurrentRevision.competition_id == domain.competition_id)
            .values(current_revision_id=first_revision_id, lock_version=2)
        )

    with session_factory.begin() as session:
        replacement_content = _content(domain, replacement=True)
        with pytest.raises(StaleItemVersionError):
            prepare_storyline_replacement(
                session,
                domain.competition_id,
                item_id,
                0,
                replacement_content,
            )
        replacement = prepare_storyline_replacement(
            session,
            domain.competition_id,
            item_id,
            1,
            replacement_content,
        )
        revision = MemoryRevision(
            id=second_revision_id,
            competition_id=domain.competition_id,
            sequence_number=3,
            previous_revision_id=first_revision_id,
            competition_season_id=domain.season_id,
            week=4,
            state_content_hash="storyline-state-two",
        )
        version = MemoryVersion(
            id=second_version_id,
            item_id=item_id,
            competition_id=domain.competition_id,
            revision_number=replacement.next_revision_number,
            content_schema_version=1,
            introduced_revision_id=second_revision_id,
            competition_season_id=domain.season_id,
            week=4,
            creating_generation_id=domain.generation_id,
        )
        persist_version_envelopes(
            session,
            revision,
            new_items=(),
            new_versions=(version,),
            retired_versions=(replacement.previous_version,),
        )
        insert_storyline_version(session, version, replacement.validated)

    manager = _manager(database_engine, domain.competition_id)
    original = manager.exact(first_version_id)
    current, historical = manager.history(item_id)

    assert original.version.retired_revision_id == second_revision_id
    assert historical.version.version_id == first_version_id
    assert current.version.version_id == second_version_id
    assert current.content.status == "resolved"
    assert current.content.related_storylines == []
    assert [evidence.version_id for evidence in current.content.evidence] == [
        domain.historical_fact_version_id
    ]
    assert domain.current_fact_version_id not in {
        evidence.version_id for evidence in original.content.evidence
    }

    with session_factory() as session:
        projections = session.scalars(
            sa.select(MemorySearchDocument)
            .where(MemorySearchDocument.item_id == item_id)
            .order_by(MemorySearchDocument.week)
        ).all()
    assert len(projections) == 2
    assert projections[0].builder_version == STORYLINE_DOCUMENT_BUILDER_VERSION
    assert projections[0].evidence_version_ids == sorted(
        [domain.historical_fact_version_id, domain.event_version_id],
        key=str,
    )

    with pytest.raises(TargetNotFoundError):
        manager.exact(domain.cross_storyline_version_id)


def test_storyline_reference_validation_enforces_kind_and_competition(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    session_factory = create_session_factory(database_engine)
    content = _content(domain)
    wrong_evidence = content.model_copy(
        update={
            "evidence": [
                content.evidence[0].model_copy(
                    update={"version_id": domain.related_storyline_version_id}
                )
            ]
        }
    )
    cross_competition_relationship = content.model_copy(
        update={
            "related_storylines": [
                content.related_storylines[0].model_copy(
                    update={"item_id": domain.cross_storyline_item_id}
                )
            ]
        }
    )

    with session_factory() as session:
        with pytest.raises(WrongTargetKindError):
            prepare_storyline_write(session, domain.competition_id, wrong_evidence)
        with pytest.raises(CrossCompetitionReferenceError):
            prepare_storyline_write(
                session,
                domain.competition_id,
                cross_competition_relationship,
            )
        with pytest.raises(WrongTargetKindError):
            prepare_storyline_replacement(
                session,
                domain.competition_id,
                domain.event_item_id,
                1,
                content,
            )


def test_storyline_write_rolls_back_typed_content_and_projection(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    session_factory = create_session_factory(database_engine)
    item_id = uuid4()
    version_id = uuid4()
    revision_id = uuid4()

    with pytest.raises(RuntimeError, match="abort canonical write"):
        with session_factory.begin() as session:
            revision = MemoryRevision(
                id=revision_id,
                competition_id=domain.competition_id,
                sequence_number=2,
                previous_revision_id=domain.current_revision_id,
                competition_season_id=domain.season_id,
                week=3,
                state_content_hash="must-roll-back",
            )
            item = MemoryItem(
                id=item_id,
                competition_id=domain.competition_id,
                kind="storyline",
            )
            version = MemoryVersion(
                id=version_id,
                item_id=item_id,
                competition_id=domain.competition_id,
                revision_number=1,
                content_schema_version=1,
                introduced_revision_id=revision_id,
                competition_season_id=domain.season_id,
                week=3,
                creating_generation_id=domain.generation_id,
            )
            persist_version_envelopes(
                session,
                revision,
                new_items=(item,),
                new_versions=(version,),
            )
            prepared = prepare_storyline_write(
                session,
                domain.competition_id,
                _content(domain),
            )
            insert_storyline_version(session, version, prepared)
            session.flush()
            raise RuntimeError("abort canonical write")

    with database_engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(StorylineVersion)
            .where(StorylineVersion.version_id == version_id)
        ) == 0
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(MemorySearchDocument)
            .where(MemorySearchDocument.version_id == version_id)
        ) == 0
