from collections.abc import Mapping
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from backend.database.models.core import (
    Competition,
    CompetitionSeason,
    Franchise,
    SeasonRoster,
)
from backend.database.models.memory import (
    ContextNote,
    CurrentRevision,
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
    StorylineVersion,
    TriggerVersion,
)


def _seed_domain(connection: Connection, label: str) -> dict[str, UUID]:
    ids = {
        "competition": uuid4(),
        "season": uuid4(),
        "franchise": uuid4(),
        "roster": uuid4(),
    }
    connection.execute(
        sa.insert(Competition),
        {"id": ids["competition"], "display_name": f"{label} Competition"},
    )
    connection.execute(
        sa.insert(CompetitionSeason),
        {
            "id": ids["season"],
            "competition_id": ids["competition"],
            "season_year": 2026,
            "sequence_number": 1,
            "sleeper_league_id": f"league-{uuid4()}",
        },
    )
    connection.execute(
        sa.insert(Franchise),
        {
            "id": ids["franchise"],
            "competition_id": ids["competition"],
            "display_name": f"{label} Franchise",
        },
    )
    connection.execute(
        sa.insert(SeasonRoster),
        {
            "id": ids["roster"],
            "competition_id": ids["competition"],
            "competition_season_id": ids["season"],
            "franchise_id": ids["franchise"],
            "sleeper_roster_id": f"roster-{uuid4()}",
        },
    )
    return ids


def _insert_generation_if_present(
    connection: Connection,
    domain: Mapping[str, UUID],
) -> UUID:
    generation_id = uuid4()
    has_reporting = connection.scalar(
        sa.text("SELECT to_regclass('reporting.generations') IS NOT NULL")
    )
    if has_reporting:
        connection.execute(
            sa.text(
                """
                INSERT INTO reporting.generations (
                    id, competition_id, competition_season_id, kind, status,
                    request_text, requested_primary_model, settings_jsonb,
                    current_turn
                ) VALUES (
                    :id, :competition_id, :competition_season_id, 'test', 'pending',
                    'memory constraint fixture', 'test-model', '{}'::jsonb, 0
                )
                """
            ),
            {
                "id": generation_id,
                "competition_id": domain["competition"],
                "competition_season_id": domain["season"],
            },
        )
    return generation_id


def _insert_revision(
    connection: Connection,
    domain: Mapping[str, UUID],
    *,
    sequence_number: int,
    previous_revision_id: UUID | None = None,
    producing_generation_id: UUID | None = None,
) -> UUID:
    revision_id = uuid4()
    connection.execute(
        sa.insert(MemoryRevision),
        {
            "id": revision_id,
            "competition_id": domain["competition"],
            "sequence_number": sequence_number,
            "previous_revision_id": previous_revision_id,
            "producing_generation_id": producing_generation_id,
            "competition_season_id": domain["season"],
            "week": sequence_number,
            "state_content_hash": f"state-{uuid4()}",
        },
    )
    return revision_id


def _insert_item_and_version(
    connection: Connection,
    domain: Mapping[str, UUID],
    revision_id: UUID,
    *,
    kind: str = "storyline",
    revision_number: int = 1,
) -> tuple[UUID, UUID, UUID]:
    item_id = uuid4()
    version_id = uuid4()
    generation_id = _insert_generation_if_present(connection, domain)
    connection.execute(
        sa.insert(MemoryItem),
        {
            "id": item_id,
            "competition_id": domain["competition"],
            "kind": kind,
            "agent_key": f"item-{uuid4()}",
        },
    )
    connection.execute(
        sa.insert(MemoryVersion),
        {
            "id": version_id,
            "item_id": item_id,
            "competition_id": domain["competition"],
            "revision_number": revision_number,
            "introduced_revision_id": revision_id,
            "competition_season_id": domain["season"],
            "week": 1,
            "creating_generation_id": generation_id,
        },
    )
    return item_id, version_id, generation_id


def _assert_integrity_error(
    engine: Engine,
    statement: sa.Executable,
) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(statement)


def _assert_database_error(
    engine: Engine,
    statement: sa.Executable,
) -> None:
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(statement)


def test_memory_schema_keeps_only_structural_checks_and_history_guards(
    database_engine: Engine,
) -> None:
    expected_tables = {
        "memory_revisions",
        "current_revisions",
        "memory_items",
        "memory_versions",
        "storyline_versions",
        "fact_versions",
        "event_versions",
        "trigger_versions",
        "context_notes",
        "context_note_versions",
        "memory_search_documents",
    }
    expected_checks = {"ck_context_notes_scope_shape"}
    expected_triggers = {
        "memory_revisions_reject_mutation",
        "memory_items_reject_mutation",
        "storyline_versions_reject_mutation",
        "fact_versions_reject_mutation",
        "event_versions_reject_mutation",
        "trigger_versions_reject_mutation",
        "context_notes_reject_mutation",
        "context_note_versions_reject_mutation",
        "memory_versions_protect_history",
        "current_revisions_protect_concurrency",
    }

    with database_engine.connect() as connection:
        tables = set(
            connection.execute(
                sa.text(
                    """
                    SELECT tablename
                    FROM pg_catalog.pg_tables
                    WHERE schemaname = 'memory'
                    """
                )
            ).scalars()
        )
        checks = set(
            connection.execute(
                sa.text(
                    """
                    SELECT postgres_constraints.conname
                    FROM pg_catalog.pg_constraint AS postgres_constraints
                    JOIN pg_catalog.pg_namespace AS namespaces
                      ON namespaces.oid = postgres_constraints.connamespace
                    WHERE namespaces.nspname = 'memory'
                      AND postgres_constraints.contype = 'c'
                    """
                )
            ).scalars()
        )
        triggers = set(
            connection.execute(
                sa.text(
                    """
                    SELECT trigger_name
                    FROM information_schema.triggers
                    WHERE trigger_schema = 'memory'
                    """
                )
            ).scalars()
        )
        delete_rules = set(
            connection.execute(
                sa.text(
                    """
                    SELECT delete_rule
                    FROM information_schema.referential_constraints
                    WHERE constraint_schema = 'memory'
                    """
                )
            ).scalars()
        )
        uuid_defaults = connection.execute(
            sa.text(
                """
                SELECT table_name, column_default
                FROM information_schema.columns
                WHERE table_schema = 'memory'
                  AND column_name = 'id'
                  AND table_name IN (
                      'memory_revisions', 'memory_items', 'memory_versions'
                  )
                """
            )
        ).all()

    assert expected_tables == tables
    assert expected_checks == checks
    assert expected_triggers <= triggers
    assert delete_rules == {"RESTRICT"}
    assert len(uuid_defaults) == 3
    assert all(default is None for _, default in uuid_defaults)


def test_database_accepts_application_validated_memory_semantics(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Semantic Boundary")
        revision_id = _insert_revision(
            connection,
            domain,
            sequence_number=-9,
        )
        item_id, version_id, _ = _insert_item_and_version(
            connection,
            domain,
            revision_id,
            kind="future_memory_kind",
            revision_number=-4,
        )
        connection.execute(
            sa.update(MemoryVersion)
            .where(MemoryVersion.id == version_id)
            .values(retired_revision_id=revision_id)
        )
        connection.execute(
            sa.insert(StorylineVersion),
            {
                "version_id": version_id,
                "headline": "",
                "summary": "",
                "status": "future_status",
                "salience": -100,
                "tags": [],
            },
        )

    with database_engine.connect() as connection:
        row = connection.execute(
            sa.select(MemoryItem.kind, MemoryVersion.revision_number)
            .join(MemoryVersion, MemoryVersion.item_id == MemoryItem.id)
            .where(MemoryItem.id == item_id)
        ).one()
    assert row == ("future_memory_kind", -4)


def test_memory_scope_isolation_rejects_cross_competition_ids(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        first = _seed_domain(connection, "First")
        second = _seed_domain(connection, "Second")
        first_revision = _insert_revision(connection, first, sequence_number=0)
        second_revision = _insert_revision(connection, second, sequence_number=0)
        first_item, first_version, first_generation = _insert_item_and_version(
            connection,
            first,
            first_revision,
        )
        second_item, _, _ = _insert_item_and_version(
            connection,
            second,
            second_revision,
        )

    invalid_statements = [
        sa.insert(MemoryRevision).values(
            id=uuid4(),
            competition_id=first["competition"],
            sequence_number=10,
            previous_revision_id=second_revision,
            state_content_hash="cross-competition-previous",
        ),
        sa.insert(CurrentRevision).values(
            competition_id=first["competition"],
            current_revision_id=second_revision,
            lock_version=0,
        ),
        sa.insert(MemoryVersion).values(
            id=uuid4(),
            item_id=second_item,
            competition_id=first["competition"],
            revision_number=10,
            introduced_revision_id=first_revision,
            creating_generation_id=first_generation,
        ),
        sa.insert(MemoryVersion).values(
            id=uuid4(),
            item_id=first_item,
            competition_id=first["competition"],
            revision_number=11,
            introduced_revision_id=second_revision,
            creating_generation_id=first_generation,
        ),
        sa.insert(MemoryVersion).values(
            id=uuid4(),
            item_id=first_item,
            competition_id=first["competition"],
            revision_number=12,
            introduced_revision_id=first_revision,
            competition_season_id=second["season"],
            creating_generation_id=first_generation,
        ),
        sa.insert(TriggerVersion).values(
            version_id=first_version,
            competition_id=first["competition"],
            trigger_type="test",
            status="open",
            fire_policy="one_shot",
            target_competition_season_id=second["season"],
            condition={},
        ),
        sa.insert(ContextNote).values(
            item_id=first_item,
            competition_id=first["competition"],
            scope="competition_season",
            competition_season_id=second["season"],
            note_key="cross-scope",
        ),
    ]
    for statement in invalid_statements:
        _assert_integrity_error(database_engine, statement)


def test_current_pointer_and_revision_uniqueness_support_stale_writer_rejection(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Concurrency")
        other_domain = _seed_domain(connection, "Other Concurrency")
        root_revision = _insert_revision(connection, domain, sequence_number=0)
        other_revision = _insert_revision(
            connection,
            other_domain,
            sequence_number=0,
        )
        next_revision = _insert_revision(
            connection,
            domain,
            sequence_number=1,
            previous_revision_id=root_revision,
        )
        generation_id = _insert_generation_if_present(connection, domain)
        _insert_revision(
            connection,
            domain,
            sequence_number=2,
            previous_revision_id=next_revision,
            producing_generation_id=generation_id,
        )
        connection.execute(
            sa.insert(CurrentRevision),
            {
                "competition_id": domain["competition"],
                "current_revision_id": root_revision,
                "lock_version": 0,
            },
        )

    _assert_database_error(
        database_engine,
        sa.update(CurrentRevision)
        .where(CurrentRevision.competition_id == domain["competition"])
        .values(current_revision_id=next_revision, lock_version=0),
    )

    with database_engine.begin() as connection:
        result = connection.execute(
            sa.update(CurrentRevision)
            .where(CurrentRevision.competition_id == domain["competition"])
            .where(CurrentRevision.lock_version == 0)
            .values(current_revision_id=next_revision, lock_version=1)
        )
        assert result.rowcount == 1

    with database_engine.begin() as connection:
        stale_result = connection.execute(
            sa.update(CurrentRevision)
            .where(CurrentRevision.competition_id == domain["competition"])
            .where(CurrentRevision.lock_version == 0)
            .values(current_revision_id=root_revision, lock_version=1)
        )
        assert stale_result.rowcount == 0

    _assert_database_error(
        database_engine,
        sa.update(CurrentRevision)
        .where(CurrentRevision.competition_id == domain["competition"])
        .values(
            competition_id=other_domain["competition"],
            current_revision_id=other_revision,
            lock_version=2,
        ),
    )

    _assert_integrity_error(
        database_engine,
        sa.insert(MemoryRevision).values(
            id=uuid4(),
            competition_id=domain["competition"],
            sequence_number=1,
            previous_revision_id=root_revision,
            state_content_hash="duplicate-sequence",
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(CurrentRevision).values(
            competition_id=domain["competition"],
            current_revision_id=next_revision,
            lock_version=1,
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(MemoryRevision).values(
            id=uuid4(),
            competition_id=domain["competition"],
            sequence_number=3,
            previous_revision_id=next_revision,
            producing_generation_id=generation_id,
            state_content_hash="duplicate-producing-generation",
        ),
    )
    _assert_database_error(
        database_engine,
        sa.delete(CurrentRevision).where(
            CurrentRevision.competition_id == domain["competition"]
        ),
    )


def test_memory_version_and_search_document_identity_is_unique(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Unique Memory")
        revision_id = _insert_revision(connection, domain, sequence_number=0)
        source_item, source_version, generation_id = _insert_item_and_version(
            connection,
            domain,
            revision_id,
        )
        connection.execute(
            sa.insert(MemorySearchDocument),
            {
                "version_id": source_version,
                "item_id": source_item,
                "competition_id": domain["competition"],
                "kind": "storyline",
                "document_text": "A searchable storyline",
                "builder_version": 1,
                "content_hash": "search-document-hash",
            },
        )

    _assert_integrity_error(
        database_engine,
        sa.insert(MemoryVersion).values(
            id=uuid4(),
            item_id=source_item,
            competition_id=domain["competition"],
            revision_number=1,
            introduced_revision_id=revision_id,
            creating_generation_id=generation_id,
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(MemorySearchDocument).values(
            version_id=source_version,
            item_id=source_item,
            competition_id=domain["competition"],
            kind="storyline",
            document_text="Duplicate projection",
            builder_version=1,
            content_hash="duplicate-hash",
        ),
    )


def test_canonical_history_is_immutable_except_one_retirement(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Immutable")
        root_revision = _insert_revision(connection, domain, sequence_number=0)
        retirement_revision = _insert_revision(
            connection,
            domain,
            sequence_number=1,
            previous_revision_id=root_revision,
        )
        later_revision = _insert_revision(
            connection,
            domain,
            sequence_number=2,
            previous_revision_id=retirement_revision,
        )
        item_id, version_id, _ = _insert_item_and_version(
            connection,
            domain,
            root_revision,
        )
        connection.execute(
            sa.insert(StorylineVersion),
            {
                "version_id": version_id,
                "headline": "Immutable headline",
                "summary": "Immutable summary",
                "status": "active",
                "salience": 3,
                "tags": [],
            },
        )

    _assert_database_error(
        database_engine,
        sa.update(MemoryRevision)
        .where(MemoryRevision.id == root_revision)
        .values(state_content_hash="changed"),
    )
    _assert_database_error(
        database_engine,
        sa.delete(MemoryItem).where(MemoryItem.id == item_id),
    )
    _assert_database_error(
        database_engine,
        sa.update(MemoryVersion)
        .where(MemoryVersion.id == version_id)
        .values(change_reason="changed"),
    )

    with database_engine.begin() as connection:
        result = connection.execute(
            sa.update(MemoryVersion)
            .where(MemoryVersion.id == version_id)
            .values(retired_revision_id=retirement_revision)
        )
        assert result.rowcount == 1

    _assert_database_error(
        database_engine,
        sa.update(MemoryVersion)
        .where(MemoryVersion.id == version_id)
        .values(retired_revision_id=later_revision),
    )
    _assert_database_error(
        database_engine,
        sa.delete(MemoryVersion).where(MemoryVersion.id == version_id),
    )
    _assert_database_error(
        database_engine,
        sa.update(StorylineVersion)
        .where(StorylineVersion.version_id == version_id)
        .values(headline="changed"),
    )


def test_context_note_scope_shape_and_keys_are_unambiguous(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Context")
        second_franchise = uuid4()
        connection.execute(
            sa.insert(Franchise),
            {
                "id": second_franchise,
                "competition_id": domain["competition"],
                "display_name": "Second Franchise",
            },
        )
        item_ids = [uuid4() for _ in range(5)]
        connection.execute(
            sa.insert(MemoryItem),
            [
                {
                    "id": item_id,
                    "competition_id": domain["competition"],
                    "kind": "context_note",
                }
                for item_id in item_ids
            ],
        )
        connection.execute(
            sa.insert(ContextNote),
            {
                "item_id": item_ids[0],
                "competition_id": domain["competition"],
                "scope": "competition",
                "note_key": "overview",
            },
        )
        connection.execute(
            sa.insert(ContextNote),
            [
                {
                    "item_id": item_ids[2],
                    "competition_id": domain["competition"],
                    "scope": "franchise",
                    "franchise_id": domain["franchise"],
                    "note_key": "identity",
                },
                {
                    "item_id": item_ids[3],
                    "competition_id": domain["competition"],
                    "scope": "franchise",
                    "franchise_id": second_franchise,
                    "note_key": "identity",
                },
            ],
        )

    _assert_integrity_error(
        database_engine,
        sa.insert(ContextNote).values(
            item_id=item_ids[1],
            competition_id=domain["competition"],
            scope="competition",
            note_key="overview",
        ),
    )
    _assert_integrity_error(
        database_engine,
        sa.insert(ContextNote).values(
            item_id=item_ids[4],
            competition_id=domain["competition"],
            scope="franchise",
            note_key="missing-target",
        ),
    )


def test_typed_payloads_are_canonical_and_search_documents_are_rebuildable(
    database_engine: Engine,
) -> None:
    with database_engine.begin() as connection:
        domain = _seed_domain(connection, "Typed Search")
        revision_id = _insert_revision(connection, domain, sequence_number=0)
        item_id, version_id, _ = _insert_item_and_version(
            connection,
            domain,
            revision_id,
        )
        evidence_version_id = uuid4()
        related_item_id = uuid4()
        subjects = [
            {
                "kind": "franchise",
                "id": str(domain["franchise"]),
                "role": "focus",
            }
        ]
        evidence = [
            {
                "kind": "fact",
                "version_id": str(evidence_version_id),
                "role": "support",
            }
        ]
        related_storylines = [
            {"item_id": str(related_item_id), "role": "counterpoint"}
        ]
        connection.execute(
            sa.insert(StorylineVersion),
            {
                "version_id": version_id,
                "headline": "Playoff collapse",
                "summary": "A typed storyline with exact evidence.",
                "status": "active",
                "salience": 4,
                "tags": ["playoffs"],
                "subjects": subjects,
                "evidence": evidence,
                "related_storylines": related_storylines,
            },
        )
        connection.execute(
            sa.insert(MemorySearchDocument),
            {
                "version_id": version_id,
                "item_id": item_id,
                "competition_id": domain["competition"],
                "kind": "storyline",
                "status": "active",
                "salience": 4,
                "competition_season_id": domain["season"],
                "week": 1,
                "entity_keys": [f"franchise:{domain['franchise']}"],
                "evidence_version_ids": [evidence_version_id],
                "related_item_ids": [related_item_id],
                "tags": ["playoffs"],
                "document_text": "Playoff collapse for the focus franchise",
                "builder_version": 1,
                "content_hash": "typed-search-v1",
            },
        )

    with database_engine.connect() as connection:
        stored = connection.execute(
            sa.select(
                MemoryVersion.content_schema_version,
                StorylineVersion.subjects,
                StorylineVersion.evidence,
                StorylineVersion.related_storylines,
            )
            .join(StorylineVersion, StorylineVersion.version_id == MemoryVersion.id)
            .where(MemoryVersion.id == version_id)
        ).one()
        lexical_match = connection.scalar(
            sa.select(sa.func.count())
            .select_from(MemorySearchDocument)
            .where(
                MemorySearchDocument.search_vector.op("@@")(
                    sa.func.plainto_tsquery("english", "playoff collapse")
                )
            )
        )

    assert stored == (1, subjects, evidence, related_storylines)
    assert lexical_match == 1

    with database_engine.begin() as connection:
        connection.execute(
            sa.update(MemorySearchDocument)
            .where(MemorySearchDocument.version_id == version_id)
            .values(
                document_text="Rebuilt projection",
                builder_version=2,
                content_hash="typed-search-v2",
            )
        )
        connection.execute(
            sa.delete(MemorySearchDocument).where(
                MemorySearchDocument.version_id == version_id
            )
        )
