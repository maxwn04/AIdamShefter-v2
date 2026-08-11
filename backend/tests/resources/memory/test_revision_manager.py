from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.core import Competition, CompetitionSeason, Franchise
from backend.database.models.memory import (
    CurrentRevision,
    FactVersion,
    MemoryItem,
    MemoryRevision,
    MemoryVersion,
    StorylineVersion,
)
from backend.database.models.reporting import Generation
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common import StaleCanonicalRevisionError
from backend.resources.memory.revisions.manager import RevisionManager
from backend.resources.memory.revisions.shared import visible_versions_statement
from backend.resources.memory.revisions.writers import lock_current_revision
from backend.tests.database.conftest import database_engine, migrated_database


@dataclass(frozen=True)
class SeededMemory:
    competition_id: UUID
    franchise_id: UUID
    first_revision_id: UUID
    current_revision_id: UUID
    storyline_item_id: UUID
    first_storyline_version_id: UUID
    current_storyline_version_id: UUID
    evidence_version_id: UUID


def _seed_memory_timeline(database_engine: Engine) -> SeededMemory:
    competition_id = uuid4()
    season_id = uuid4()
    franchise_id = uuid4()
    generation_id = uuid4()
    first_revision_id = uuid4()
    current_revision_id = uuid4()
    storyline_item_id = uuid4()
    fact_item_id = uuid4()
    first_storyline_version_id = uuid4()
    current_storyline_version_id = uuid4()
    evidence_version_id = uuid4()

    with database_engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": competition_id, "display_name": "Revision Proof League"},
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": season_id,
                "competition_id": competition_id,
                "season_year": 2026,
                "sequence_number": 1,
                "sleeper_league_id": f"league-{uuid4()}",
            },
        )
        connection.execute(
            sa.insert(Franchise),
            {
                "id": franchise_id,
                "competition_id": competition_id,
                "display_name": "Revision Proof Franchise",
            },
        )
        connection.execute(
            sa.insert(Generation),
            {
                "id": generation_id,
                "competition_id": competition_id,
                "competition_season_id": season_id,
                "kind": "test",
                "status": "pending",
                "request_text": "seed revision query proofs",
                "requested_primary_model": "test-model",
                "settings_jsonb": {},
                "current_turn": 0,
            },
        )
        connection.execute(
            sa.insert(MemoryRevision),
            [
                {
                    "id": first_revision_id,
                    "competition_id": competition_id,
                    "sequence_number": 0,
                    "previous_revision_id": None,
                    "competition_season_id": season_id,
                    "week": 1,
                    "state_content_hash": "state-r0",
                },
                {
                    "id": current_revision_id,
                    "competition_id": competition_id,
                    "sequence_number": 1,
                    "previous_revision_id": first_revision_id,
                    "competition_season_id": season_id,
                    "week": 2,
                    "state_content_hash": "state-r1",
                },
            ],
        )
        connection.execute(
            sa.insert(CurrentRevision),
            {
                "competition_id": competition_id,
                "current_revision_id": current_revision_id,
                "lock_version": 1,
            },
        )
        connection.execute(
            sa.insert(MemoryItem),
            [
                {
                    "id": storyline_item_id,
                    "competition_id": competition_id,
                    "kind": "storyline",
                },
                {
                    "id": fact_item_id,
                    "competition_id": competition_id,
                    "kind": "fact",
                },
            ],
        )
        connection.execute(
            sa.insert(MemoryVersion),
            [
                {
                    "id": first_storyline_version_id,
                    "item_id": storyline_item_id,
                    "competition_id": competition_id,
                    "revision_number": 1,
                    "introduced_revision_id": first_revision_id,
                    "retired_revision_id": current_revision_id,
                    "competition_season_id": season_id,
                    "week": 1,
                    "creating_generation_id": generation_id,
                },
                {
                    "id": current_storyline_version_id,
                    "item_id": storyline_item_id,
                    "competition_id": competition_id,
                    "revision_number": 2,
                    "introduced_revision_id": current_revision_id,
                    "retired_revision_id": None,
                    "competition_season_id": season_id,
                    "week": 2,
                    "creating_generation_id": generation_id,
                },
                {
                    "id": evidence_version_id,
                    "item_id": fact_item_id,
                    "competition_id": competition_id,
                    "revision_number": 1,
                    "introduced_revision_id": first_revision_id,
                    "retired_revision_id": None,
                    "competition_season_id": season_id,
                    "week": 1,
                    "creating_generation_id": generation_id,
                },
            ],
        )
        connection.execute(
            sa.insert(FactVersion),
            {
                "version_id": evidence_version_id,
                "competition_id": competition_id,
                "claim": "The franchise won its opener.",
                "category": "result",
                "structured_numbers": {"wins": 1},
                "confidence": "unverified",
                "subjects": [],
                "originating_event_version_ids": [],
                "status": "active",
            },
        )

        for version_id, headline in (
            (first_storyline_version_id, "An opening statement"),
            (current_storyline_version_id, "The follow-up"),
        ):
            connection.execute(
                sa.insert(StorylineVersion),
                {
                    "version_id": version_id,
                    "headline": headline,
                    "summary": "A seeded storyline for revision query proofs.",
                    "status": "active",
                    "salience": 3,
                    "tags": ["proof"],
                    "subjects": [
                        {
                            "kind": "franchise",
                            "id": str(franchise_id),
                            "role": "focus",
                        }
                    ],
                    "evidence": [
                        {
                            "kind": "fact",
                            "version_id": str(evidence_version_id),
                            "role": "support",
                        }
                    ],
                    "related_storylines": [],
                },
            )

    return SeededMemory(
        competition_id=competition_id,
        franchise_id=franchise_id,
        first_revision_id=first_revision_id,
        current_revision_id=current_revision_id,
        storyline_item_id=storyline_item_id,
        first_storyline_version_id=first_storyline_version_id,
        current_storyline_version_id=current_storyline_version_id,
        evidence_version_id=evidence_version_id,
    )


def _manager(database_engine: Engine, competition_id: UUID) -> RevisionManager:
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "local_user"},
            "scope": {"kind": "competition", "competition_id": competition_id},
            "correlation_id": uuid4(),
        }
    )
    return RevisionManager(create_session_factory(database_engine), context)


def test_revision_manager_reads_current_pin_and_history(
    database_engine: Engine,
) -> None:
    seeded = _seed_memory_timeline(database_engine)
    manager = _manager(database_engine, seeded.competition_id)

    current = manager.current()
    pinned = manager.pin(seeded.first_revision_id)
    history = manager.history()

    assert current.revision_id == seeded.current_revision_id
    assert current.sequence_number == 1
    assert pinned.revision_id == seeded.first_revision_id
    assert pinned.sequence_number == 0
    assert [revision.sequence_number for revision in history] == [1, 0]


def test_visible_storyline_queries_prove_entity_evidence_history_and_r_plus_one_exclusion(
    database_engine: Engine,
) -> None:
    seeded = _seed_memory_timeline(database_engine)
    manager = _manager(database_engine, seeded.competition_id)

    first_revision = manager.pin(seeded.first_revision_id)
    current_revision = manager.current()

    with create_session_factory(database_engine)() as session:
        first_visible = visible_versions_statement(
            seeded.competition_id,
            first_revision.revision_id,
        ).subquery()
        first_entity_versions = tuple(
            session.scalars(
                sa.select(StorylineVersion.version_id)
                .join(
                    first_visible,
                    first_visible.c.id == StorylineVersion.version_id,
                )
                .where(
                    StorylineVersion.status == "active",
                    StorylineVersion.subjects.contains(
                        [
                            {
                                "kind": "franchise",
                                "id": str(seeded.franchise_id),
                            }
                        ]
                    ),
                )
            )
        )
        first_evidence_versions = tuple(
            session.scalars(
                sa.select(StorylineVersion.version_id)
                .join(
                    first_visible,
                    first_visible.c.id == StorylineVersion.version_id,
                )
                .where(
                    StorylineVersion.evidence.contains(
                        [
                            {
                                "kind": "fact",
                                "version_id": str(seeded.evidence_version_id),
                            }
                        ]
                    ),
                )
            )
        )

        current_visible = visible_versions_statement(
            seeded.competition_id,
            current_revision.revision_id,
        ).subquery()
        current_entity_versions = tuple(
            session.scalars(
                sa.select(StorylineVersion.version_id)
                .join(
                    current_visible,
                    current_visible.c.id == StorylineVersion.version_id,
                )
                .where(
                    StorylineVersion.status == "active",
                    StorylineVersion.subjects.contains(
                        [
                            {
                                "kind": "franchise",
                                "id": str(seeded.franchise_id),
                            }
                        ]
                    ),
                )
            )
        )
        history = tuple(
            session.scalars(
                sa.select(MemoryVersion.id)
                .where(MemoryVersion.item_id == seeded.storyline_item_id)
                .order_by(MemoryVersion.revision_number)
            )
        )

    assert first_entity_versions == (seeded.first_storyline_version_id,)
    assert first_evidence_versions == (seeded.first_storyline_version_id,)
    assert seeded.current_storyline_version_id not in first_entity_versions
    assert current_entity_versions == (seeded.current_storyline_version_id,)
    assert history == (
        seeded.first_storyline_version_id,
        seeded.current_storyline_version_id,
    )


def test_revision_parent_allocates_from_current_and_rejects_stale(
    database_engine: Engine,
) -> None:
    seeded = _seed_memory_timeline(database_engine)
    session_factory = create_session_factory(database_engine)

    with session_factory.begin() as session:
        parent = lock_current_revision(
            session,
            seeded.competition_id,
            seeded.current_revision_id,
        )
    assert parent.current_revision_id == seeded.current_revision_id
    assert parent.next_sequence_number == 2
    assert parent.next_lock_version == 2

    with pytest.raises(StaleCanonicalRevisionError), session_factory.begin() as session:
        lock_current_revision(
            session,
            seeded.competition_id,
            seeded.first_revision_id,
        )
