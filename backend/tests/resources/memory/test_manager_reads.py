from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from backend.database.models.core import Competition, CompetitionSeason
from backend.database.models.memory import (
    CurrentRevision,
    FactVersion,
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
    StorylineVersion,
)
from backend.database.models.reporting import Generation
from backend.database.sessions import create_session_factory
from backend.resources.memory.errors import (
    MemoryScopeViolation,
    SearchProjectionUnavailable,
)
from backend.resources.memory.manager import MemoryManager
from backend.resources.memory.objects import (
    ExpansionPolicy,
    MemoryKind,
    MemoryListQuery,
    MemoryQuery,
    MemoryStatus,
)
from backend.tests.database.conftest import (  # noqa: F401
    database_engine,
    migrated_database,
)


@dataclass(frozen=True)
class _SeededMemory:
    competition_id: UUID
    other_competition_id: UUID
    season_id: UUID
    root_revision_id: UUID
    middle_revision_id: UUID
    current_revision_id: UUID
    storyline_item_id: UUID
    first_storyline_version_id: UUID
    current_storyline_version_id: UUID
    fact_version_id: UUID


def _seed_memory(engine: Engine) -> _SeededMemory:
    competition_id = uuid4()
    other_competition_id = uuid4()
    season_id = uuid4()
    other_season_id = uuid4()
    root_revision_id = uuid4()
    middle_revision_id = uuid4()
    current_revision_id = uuid4()
    other_revision_id = uuid4()
    middle_generation_id = uuid4()
    current_generation_id = uuid4()
    storyline_item_id = uuid4()
    fact_item_id = uuid4()
    first_storyline_version_id = uuid4()
    current_storyline_version_id = uuid4()
    fact_version_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            [
                {"id": competition_id, "display_name": "Manager Test League"},
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
            sa.insert(MemoryRevision),
            [
                {
                    "id": root_revision_id,
                    "competition_id": competition_id,
                    "sequence_number": 0,
                    "previous_revision_id": None,
                    "competition_season_id": None,
                    "week": None,
                    "producing_generation_id": None,
                    "state_content_hash": "root",
                },
                {
                    "id": other_revision_id,
                    "competition_id": other_competition_id,
                    "sequence_number": 0,
                    "previous_revision_id": None,
                    "competition_season_id": None,
                    "week": None,
                    "producing_generation_id": None,
                    "state_content_hash": "other-root",
                },
            ],
        )
        connection.execute(
            sa.insert(Generation),
            {
                "id": middle_generation_id,
                "competition_id": competition_id,
                "competition_season_id": season_id,
                "input_memory_revision_id": root_revision_id,
                "kind": "test",
                "status": "complete",
                "request_text": "manager read fixture",
                "requested_primary_model": "test-model",
                "settings_jsonb": {},
                "current_turn": 0,
            },
        )
        connection.execute(
            sa.insert(MemoryRevision),
            {
                "id": middle_revision_id,
                "competition_id": competition_id,
                "sequence_number": 1,
                "previous_revision_id": root_revision_id,
                "producing_generation_id": middle_generation_id,
                "competition_season_id": season_id,
                "week": 7,
                "state_content_hash": "middle",
            },
        )
        connection.execute(
            sa.insert(Generation),
            {
                "id": current_generation_id,
                "competition_id": competition_id,
                "competition_season_id": season_id,
                "input_memory_revision_id": middle_revision_id,
                "kind": "test",
                "status": "complete",
                "request_text": "manager replacement fixture",
                "requested_primary_model": "test-model",
                "settings_jsonb": {},
                "current_turn": 0,
            },
        )
        connection.execute(
            sa.insert(MemoryRevision),
            {
                "id": current_revision_id,
                "competition_id": competition_id,
                "sequence_number": 2,
                "previous_revision_id": middle_revision_id,
                "producing_generation_id": current_generation_id,
                "competition_season_id": season_id,
                "week": 8,
                "state_content_hash": "current",
            },
        )
        connection.execute(
            sa.insert(CurrentRevision),
            [
                {
                    "competition_id": competition_id,
                    "current_revision_id": current_revision_id,
                    "lock_version": 2,
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
                {
                    "id": storyline_item_id,
                    "competition_id": competition_id,
                    "kind": "storyline",
                    "agent_key": "collapse-arc",
                },
                {
                    "id": fact_item_id,
                    "competition_id": competition_id,
                    "kind": "fact",
                    "agent_key": "loss-streak",
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
                    "introduced_revision_id": middle_revision_id,
                    "retired_revision_id": current_revision_id,
                    "competition_season_id": season_id,
                    "week": 7,
                    "creating_generation_id": middle_generation_id,
                    "change_reason": None,
                },
                {
                    "id": current_storyline_version_id,
                    "item_id": storyline_item_id,
                    "competition_id": competition_id,
                    "revision_number": 2,
                    "introduced_revision_id": current_revision_id,
                    "retired_revision_id": None,
                    "competition_season_id": season_id,
                    "week": 8,
                    "creating_generation_id": current_generation_id,
                    "change_reason": "The arc resolved",
                },
                {
                    "id": fact_version_id,
                    "item_id": fact_item_id,
                    "competition_id": competition_id,
                    "revision_number": 1,
                    "introduced_revision_id": middle_revision_id,
                    "retired_revision_id": None,
                    "competition_season_id": season_id,
                    "week": 7,
                    "creating_generation_id": middle_generation_id,
                    "change_reason": None,
                },
            ],
        )
        connection.execute(
            sa.insert(StorylineVersion),
            [
                {
                    "version_id": first_storyline_version_id,
                    "headline": "The Collapse Begins",
                    "summary": "The Sharks keep losing.",
                    "status": "active",
                    "arc_type": "collapse",
                    "salience": 4,
                    "tags": ["playoffs"],
                    "subjects": [],
                    "evidence": [],
                    "related_storylines": [],
                    "resolution_summary": None,
                },
                {
                    "version_id": current_storyline_version_id,
                    "headline": "The Collapse Is Complete",
                    "summary": "The Sharks missed the playoffs.",
                    "status": "resolved",
                    "arc_type": "collapse",
                    "salience": 5,
                    "tags": ["playoffs"],
                    "subjects": [],
                    "evidence": [
                        {
                            "kind": "fact",
                            "version_id": str(fact_version_id),
                            "role": "payoff",
                        }
                    ],
                    "related_storylines": [],
                    "resolution_summary": "The late-season slide ended the run.",
                },
            ],
        )
        connection.execute(
            sa.insert(FactVersion),
            {
                "version_id": fact_version_id,
                "competition_id": competition_id,
                "claim": "The Sharks lost three straight games.",
                "category": "streak",
                "structured_numbers": {"losses": 3},
                "confidence": "source_backed",
                "status": "active",
                "subjects": [],
                "originating_event_version_ids": [],
            },
        )

    return _SeededMemory(
        competition_id=competition_id,
        other_competition_id=other_competition_id,
        season_id=season_id,
        root_revision_id=root_revision_id,
        middle_revision_id=middle_revision_id,
        current_revision_id=current_revision_id,
        storyline_item_id=storyline_item_id,
        first_storyline_version_id=first_storyline_version_id,
        current_storyline_version_id=current_storyline_version_id,
        fact_version_id=fact_version_id,
    )


def _manager(engine: Engine) -> MemoryManager:
    return MemoryManager(create_session_factory(engine))


def test_revision_resolution_is_competition_scoped(database_engine: Engine) -> None:
    seeded = _seed_memory(database_engine)
    manager = _manager(database_engine)

    current = manager.current_revision(seeded.competition_id)

    assert current.id == seeded.current_revision_id
    assert current.sequence_number == 2
    with pytest.raises(MemoryScopeViolation):
        manager.get_revision(current.id, seeded.other_competition_id)


def test_visible_reads_pin_versions_and_batch_expand_exact_evidence(
    database_engine: Engine,
) -> None:
    seeded = _seed_memory(database_engine)
    manager = _manager(database_engine)
    root = manager.get_revision(seeded.root_revision_id)
    middle = manager.get_revision(seeded.middle_revision_id)
    current = manager.get_revision(seeded.current_revision_id)

    with pytest.raises(MemoryScopeViolation):
        manager.get_visible_item(
            root,
            seeded.storyline_item_id,
            ExpansionPolicy(),
        )
    historical = manager.get_visible_item(
        middle,
        seeded.storyline_item_id,
        ExpansionPolicy(),
    )
    current_item = manager.get_visible_item(
        current,
        seeded.storyline_item_id,
        ExpansionPolicy(),
    )
    hydrated = manager.hydrate_visible_versions(
        current,
        [seeded.current_storyline_version_id],
        ExpansionPolicy(include_evidence=True),
    )

    assert historical.version.version_id == seeded.first_storyline_version_id
    assert current_item.version.version_id == seeded.current_storyline_version_id
    assert hydrated[seeded.current_storyline_version_id].evidence[0].version_id == (
        seeded.fact_version_id
    )
    with pytest.raises(MemoryScopeViolation):
        manager.get_visible_version(
            middle,
            seeded.current_storyline_version_id,
            ExpansionPolicy(),
        )
    with pytest.raises(MemoryScopeViolation):
        manager.get_visible_version(
            current,
            seeded.first_storyline_version_id,
            ExpansionPolicy(),
        )


def test_history_and_pages_return_typed_canonical_resources(
    database_engine: Engine,
) -> None:
    seeded = _seed_memory(database_engine)
    manager = _manager(database_engine)
    current = manager.current_revision(seeded.competition_id)

    history = manager.item_history(seeded.competition_id, seeded.storyline_item_id)
    page = manager.list_visible_items(
        current,
        MemoryListQuery(
            competition_id=seeded.competition_id,
            kinds={MemoryKind.STORYLINE},
            statuses={MemoryStatus.RESOLVED},
        ),
    )
    revisions = manager.list_revisions(seeded.competition_id, None, 2)

    assert [version.revision_number for version in history.versions] == [1, 2]
    assert [item.version.version_id for item in page.items] == [
        seeded.current_storyline_version_id
    ]
    assert [revision.sequence_number for revision in revisions.revisions] == [2, 1]
    assert revisions.next_cursor == "1"


def test_projection_rebuild_restores_search_without_changing_canonical_state(
    database_engine: Engine,
) -> None:
    seeded = _seed_memory(database_engine)
    manager = _manager(database_engine)
    current = manager.current_revision(seeded.competition_id)
    query = MemoryQuery(text="missed playoffs", limit=5)

    with pytest.raises(SearchProjectionUnavailable):
        manager.find_candidates(current, query)
    fallback = manager.scan_visible_candidates(current, query, 5)
    rebuilt = manager.rebuild_search_index(seeded.competition_id, batch_size=2)
    candidates = manager.find_candidates(current, query)
    with database_engine.begin() as connection:
        connection.execute(
            sa.update(MemorySearchDocument)
            .where(MemorySearchDocument.version_id == seeded.fact_version_id)
            .values(builder_version=99)
        )
    stale_status = manager.search_index_status(seeded.competition_id)
    with pytest.raises(SearchProjectionUnavailable):
        manager.find_candidates(current, query)
    mixed_fallback = manager.scan_visible_candidates(current, query, 5)
    manager.rebuild_search_index(seeded.competition_id, batch_size=2)
    repaired_candidates = manager.find_candidates(current, query)
    repaired_status = manager.search_index_status(seeded.competition_id)

    assert [candidate.version_id for candidate in fallback] == [
        seeded.current_storyline_version_id
    ]
    assert [candidate.version_id for candidate in candidates] == [
        seeded.current_storyline_version_id
    ]
    assert stale_status.stale_document_count == 1
    assert [candidate.version_id for candidate in mixed_fallback] == [
        seeded.current_storyline_version_id
    ]
    assert [candidate.version_id for candidate in repaired_candidates] == [
        seeded.current_storyline_version_id
    ]
    assert rebuilt.rebuilt_document_count == 3
    assert repaired_status.missing_document_count == 0
    assert repaired_status.stale_document_count == 0
    assert manager.current_revision(seeded.competition_id) == current
