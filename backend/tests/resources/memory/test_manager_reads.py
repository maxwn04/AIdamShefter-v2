from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    InvalidMemoryCursor,
    MemoryScopeViolation,
    SearchProjectionUnavailable,
)
from backend.resources.memory.manager import MemoryManager
from backend.resources.memory.cursors import (
    decode_item_cursor,
    decode_revision_cursor,
    encode_revision_cursor,
)
from backend.resources.memory.objects import (
    ExpansionPolicy,
    FranchiseKey,
    MemoryKind,
    MemoryListQuery,
    MemoryQuery,
    MemoryStatus,
)
from backend.resources.memory.search_documents import (
    SEARCH_DOCUMENT_BUILDER_VERSION,
    entity_search_key,
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
                    "related_storylines": [
                        {
                            "item_id": str(storyline_item_id),
                            "role": "continuation",
                        }
                    ],
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
                "confidence": "inferred",
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
    assert revisions.next_cursor is not None
    assert decode_revision_cursor(revisions.next_cursor).sequence_number == 1


def test_item_and_revision_cursors_are_opaque_scoped_and_revision_safe(
    database_engine: Engine,
) -> None:
    seeded = _seed_memory(database_engine)
    manager = _manager(database_engine)
    current = manager.current_revision(seeded.competition_id)
    other_revision = manager.current_revision(seeded.other_competition_id)

    page = manager.list_visible_items(
        current,
        MemoryListQuery(competition_id=seeded.competition_id, limit=1),
    )
    assert page.next_cursor is not None
    decoded_item = decode_item_cursor(page.next_cursor)
    assert decoded_item.revision_id == current.id
    with pytest.raises(InvalidMemoryCursor):
        manager.list_visible_items(
            other_revision,
            MemoryListQuery(
                competition_id=seeded.other_competition_id,
                cursor=page.next_cursor,
            ),
        )
    with pytest.raises(InvalidMemoryCursor):
        manager.list_visible_items(
            current,
            MemoryListQuery(
                competition_id=seeded.competition_id,
                cursor="not-a-cursor",
            ),
        )

    revision_cursor = encode_revision_cursor(seeded.competition_id, 2)
    revisions = manager.list_revisions(seeded.competition_id, revision_cursor, 1)
    assert revisions.revisions[0].sequence_number == 1
    with pytest.raises(InvalidMemoryCursor):
        manager.list_revisions(
            seeded.other_competition_id,
            revision_cursor,
            1,
        )
    with pytest.raises(InvalidMemoryCursor):
        manager.list_revisions(seeded.competition_id, "not-a-cursor", 1)


def test_projection_rebuild_restores_search_without_changing_canonical_state(
    database_engine: Engine,
) -> None:
    seeded = _seed_memory(database_engine)
    manager = _manager(database_engine)
    current = manager.current_revision(seeded.competition_id)
    query = MemoryQuery(text="missed playoffs", limit=5)

    with pytest.raises(SearchProjectionUnavailable):
        manager.find_candidates(current, query)
    fallback = manager.scan_visible_candidates(current, query)
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
    mixed_fallback = manager.scan_visible_candidates(current, query)
    manager.rebuild_search_index(seeded.competition_id, batch_size=2)
    repaired_candidates = manager.find_candidates(current, query)
    repaired_status = manager.search_index_status(seeded.competition_id)
    exact_evidence = manager.find_candidates(
        current,
        MemoryQuery(evidence_version_ids={seeded.fact_version_id}),
    )
    exact_related = manager.find_candidates(
        current,
        MemoryQuery(related_item_ids={seeded.storyline_item_id}),
    )
    historical = manager.find_candidates(
        manager.get_revision(seeded.middle_revision_id),
        query,
    )

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
    assert [candidate.version_id for candidate in exact_evidence] == [
        seeded.current_storyline_version_id
    ]
    assert exact_evidence[0].matched_evidence_version_ids == (
        seeded.fact_version_id,
    )
    assert [candidate.version_id for candidate in exact_related] == [
        seeded.current_storyline_version_id
    ]
    assert exact_related[0].matched_related_item_ids == (
        seeded.storyline_item_id,
    )
    assert historical == ()
    assert rebuilt.rebuilt_document_count == 3
    assert repaired_status.missing_document_count == 0
    assert repaired_status.stale_document_count == 0
    assert manager.current_revision(seeded.competition_id) == current


def test_candidate_pool_reserves_capacity_for_each_independent_signal(
    database_engine: Engine,
) -> None:
    seeded = _seed_memory(database_engine)
    manager = _manager(database_engine)
    manager.rebuild_search_index(seeded.competition_id)
    entity = FranchiseKey(id=uuid4())
    entity_version_id = uuid4()
    lexical_version_ids = [uuid4() for _ in range(25)]
    version_ids = [*lexical_version_ids, entity_version_id]
    item_ids = [uuid4() for _ in version_ids]

    with database_engine.begin() as connection:
        generation_id = connection.scalar(
            sa.select(MemoryRevision.producing_generation_id).where(
                MemoryRevision.id == seeded.current_revision_id
            )
        )
        assert generation_id is not None
        connection.execute(
            sa.insert(MemoryItem),
            [
                {
                    "id": item_id,
                    "competition_id": seeded.competition_id,
                    "kind": "fact",
                    "agent_key": f"pool-{index}",
                }
                for index, item_id in enumerate(item_ids)
            ],
        )
        newest = datetime(2026, 8, 9, tzinfo=UTC)
        connection.execute(
            sa.insert(MemoryVersion),
            [
                {
                    "id": version_id,
                    "item_id": item_id,
                    "competition_id": seeded.competition_id,
                    "revision_number": 1,
                    "introduced_revision_id": seeded.current_revision_id,
                    "competition_season_id": seeded.season_id,
                    "week": 8,
                    "creating_generation_id": generation_id,
                    "recorded_at": newest - timedelta(seconds=index),
                }
                for index, (item_id, version_id) in enumerate(
                    zip(item_ids, version_ids, strict=True)
                )
            ],
        )
        connection.execute(
            sa.insert(MemorySearchDocument),
            [
                {
                    "version_id": version_id,
                    "item_id": item_id,
                    "competition_id": seeded.competition_id,
                    "kind": "fact",
                    "status": "active",
                    "competition_season_id": seeded.season_id,
                    "week": 8,
                    "entity_keys": [],
                    "evidence_version_ids": [],
                    "related_item_ids": [],
                    "tags": [],
                    "document_text": f"crowded lexical result {index}",
                    "builder_version": SEARCH_DOCUMENT_BUILDER_VERSION,
                    "content_hash": f"lexical-{index}",
                }
                for index, (item_id, version_id) in enumerate(
                    zip(item_ids[:-1], lexical_version_ids, strict=True)
                )
            ]
            + [
                {
                    "version_id": entity_version_id,
                    "item_id": item_ids[-1],
                    "competition_id": seeded.competition_id,
                    "kind": "fact",
                    "status": "active",
                    "competition_season_id": seeded.season_id,
                    "week": 8,
                    "entity_keys": [entity_search_key(entity)],
                    "evidence_version_ids": [],
                    "related_item_ids": [],
                    "tags": [],
                    "document_text": "entity only",
                    "builder_version": SEARCH_DOCUMENT_BUILDER_VERSION,
                    "content_hash": "entity",
                }
            ],
        )

    query = MemoryQuery(text="crowded", entities=(entity,), limit=1)
    candidates = manager.find_candidates(
        manager.current_revision(seeded.competition_id),
        query,
    )

    assert entity_version_id in {candidate.version_id for candidate in candidates}
    assert len(candidates) > query.limit

    filter_query = MemoryQuery(kinds={MemoryKind.FACT}, limit=1)
    filter_candidates = manager.find_candidates(
        manager.current_revision(seeded.competition_id),
        filter_query,
    )
    assert len(filter_candidates) > filter_query.limit
