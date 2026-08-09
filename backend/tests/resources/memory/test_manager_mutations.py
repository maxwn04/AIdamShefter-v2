from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from backend.database.models.core import Competition, CompetitionSeason, Franchise
from backend.database.models.memory import (
    CurrentRevision,
    ContextNoteVersion,
    EventVersion,
    FactVersion,
    MemoryItem,
    MemoryRevision,
    MemorySearchDocument,
    MemoryVersion,
    StorylineVersion,
    TriggerVersion,
)
from backend.database.models.reporting import Generation
from backend.database.sessions import create_session_factory
from backend.resources.memory.errors import (
    CanonicalStateHashMismatch,
    InvalidMemoryReference,
    MemoryScopeViolation,
    StaleCanonicalRevision,
    UnsupportedMemorySchema,
)
from backend.resources.memory.content_codec import decode_stored_content
from backend.resources.memory.manager import MemoryManager
from backend.resources.memory.objects import (
    CreateItem,
    ContextNoteContent,
    ContextNoteIdentity,
    ContextNoteScope,
    ContextNoteStatus,
    EvidenceRef,
    EventCallbackTriggerCondition,
    EventContent,
    EventStatus,
    EventType,
    ExpansionPolicy,
    FactContent,
    FactStatus,
    MemoryConfidence,
    MemoryMutationBundle,
    MemoryKind,
    MatchupEventPayload,
    NoChange,
    PlayerRef,
    ReplaceItem,
    RevisionCommitted,
    FirePolicy,
    StorylineContent,
    StorylineStatus,
    TriggerContent,
    TriggerStatus,
    TriggerType,
)
from backend.tests.database.conftest import (  # noqa: F401
    database_engine,
    migrated_database,
)


@dataclass(frozen=True)
class _Domain:
    competition_id: UUID
    season_id: UUID
    root_revision_id: UUID
    first_franchise_id: UUID
    second_franchise_id: UUID


def _seed_domain(engine: Engine) -> _Domain:
    domain = _Domain(uuid4(), uuid4(), uuid4(), uuid4(), uuid4())
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Competition),
            {"id": domain.competition_id, "display_name": "Mutation Test League"},
        )
        connection.execute(
            sa.insert(CompetitionSeason),
            {
                "id": domain.season_id,
                "competition_id": domain.competition_id,
                "season_year": 2026,
                "sequence_number": 1,
                "sleeper_league_id": f"league-{uuid4()}",
            },
        )
        connection.execute(
            sa.insert(Franchise),
            [
                {
                    "id": domain.first_franchise_id,
                    "competition_id": domain.competition_id,
                    "display_name": "Rockets",
                },
                {
                    "id": domain.second_franchise_id,
                    "competition_id": domain.competition_id,
                    "display_name": "Owls",
                },
            ],
        )
        connection.execute(
            sa.insert(MemoryRevision),
            {
                "id": domain.root_revision_id,
                "competition_id": domain.competition_id,
                "sequence_number": 0,
                "previous_revision_id": None,
                "producing_generation_id": None,
                "competition_season_id": None,
                "week": None,
                "state_content_hash": "empty",
            },
        )
        connection.execute(
            sa.insert(CurrentRevision),
            {
                "competition_id": domain.competition_id,
                "current_revision_id": domain.root_revision_id,
                "lock_version": 0,
            },
        )
    return domain


def _generation(
    engine: Engine,
    domain: _Domain,
    input_revision_id: UUID,
    *,
    week: int = 8,
) -> UUID:
    generation_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            sa.insert(Generation),
            {
                "id": generation_id,
                "competition_id": domain.competition_id,
                "competition_season_id": domain.season_id,
                "input_memory_revision_id": input_revision_id,
                "kind": "article",
                "status": "running",
                "request_text": "mutation manager test",
                "domain_cutoff_week": week,
                "requested_primary_model": "test-model",
                "settings_jsonb": {},
                "current_turn": 0,
            },
        )
    return generation_id


def _manager(engine: Engine) -> MemoryManager:
    return MemoryManager(create_session_factory(engine))


def _fact(claim: str) -> FactContent:
    return FactContent(
        claim=claim,
        category="record",
        confidence=MemoryConfidence.INFERRED,
        status=FactStatus.ACTIVE,
    )


def test_codec_rejects_unsupported_schema_with_named_internal_error() -> None:
    with pytest.raises(UnsupportedMemorySchema, match="fact v99"):
        decode_stored_content(MemoryKind.FACT, 99, object())


def test_create_supports_same_bundle_exact_evidence_and_projection(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    generation_id = _generation(
        database_engine, domain, domain.root_revision_id
    )
    fact = CreateItem(client_key="fact", content=_fact("Rockets are 6-2"))
    storyline = CreateItem(
        client_key="arc",
        content=StorylineContent(
            headline="Rockets launch",
            summary="The contender keeps winning.",
            status=StorylineStatus.ACTIVE,
            salience=4,
            evidence=(
                EvidenceRef(
                    kind="fact",
                    version_id=fact.version_id,
                    role="support",
                ),
            ),
        ),
    )

    result = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=generation_id,
            operations=(fact, storyline),
        )
    )

    assert isinstance(result, RevisionCommitted)
    assert result.revision.sequence_number == 1
    assert {item.version_id for item in result.items} == {
        fact.version_id,
        storyline.version_id,
    }
    with database_engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(MemorySearchDocument).where(
                MemorySearchDocument.version_id.in_(
                    [fact.version_id, storyline.version_id]
                )
            )
        ) == 2
        assert connection.scalar(
            sa.select(CurrentRevision.lock_version).where(
                CurrentRevision.competition_id == domain.competition_id
            )
        ) == 1


def test_one_bundle_persists_and_decodes_every_kind_with_stable_references(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    generation_id = _generation(
        database_engine, domain, domain.root_revision_id
    )
    event = CreateItem(
        client_key="matchup-event",
        content=EventContent(
            event_type=EventType.MATCHUP,
            headline="Rockets beat Owls",
            summary="The Rockets won the featured matchup.",
            salience=4,
            confidence=MemoryConfidence.INFERRED,
            status=EventStatus.ACTIVE,
            details=MatchupEventPayload(
                winner_franchise_id=domain.first_franchise_id,
                loser_franchise_id=domain.second_franchise_id,
                sleeper_matchup_id="week-8-matchup-1",
            ),
        ),
    )
    fact = CreateItem(
        client_key="record-fact",
        content=FactContent(
            claim="Rockets are 6-2",
            category="record",
            confidence=MemoryConfidence.INFERRED,
            status=FactStatus.ACTIVE,
            originating_event_version_ids=(event.version_id,),
        ),
    )
    storyline = CreateItem(
        client_key="contender-arc",
        content=StorylineContent(
            headline="Rockets launch",
            summary="The contender keeps winning.",
            status=StorylineStatus.ACTIVE,
            salience=4,
            evidence=(
                EvidenceRef(
                    kind="fact",
                    version_id=fact.version_id,
                    role="support",
                ),
            ),
        ),
    )
    trigger = CreateItem(
        client_key="callback-trigger",
        content=TriggerContent(
            trigger_type=TriggerType.EVENT_CALLBACK,
            status=TriggerStatus.OPEN,
            fire_policy=FirePolicy.ONE_SHOT,
            target_storyline_item_id=storyline.item_id,
            origin_event_item_id=event.item_id,
            condition=EventCallbackTriggerCondition(event_type=EventType.MATCHUP),
        ),
    )
    context_note = CreateItem(
        client_key="league-tone",
        content=ContextNoteContent(
            narrative="The league treats the Rockets as the team to beat.",
            status=ContextNoteStatus.ACTIVE,
        ),
        context_note_identity=ContextNoteIdentity(
            scope=ContextNoteScope.COMPETITION,
            note_key="team-to-beat",
        ),
    )
    creates = (event, fact, storyline, trigger, context_note)

    result = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=generation_id,
            operations=creates,
        )
    )

    assert isinstance(result, RevisionCommitted)
    hydrated = _manager(database_engine).hydrate_visible_versions(
        result.revision,
        [create.version_id for create in creates],
        ExpansionPolicy(include_evidence=True, include_related_items=True),
    )
    assert set(hydrated) == {create.version_id for create in creates}
    assert hydrated[fact.version_id].evidence[0].version_id == event.version_id
    assert hydrated[storyline.version_id].evidence[0].version_id == fact.version_id
    assert {item.item_id for item in hydrated[trigger.version_id].related_items} == {
        storyline.item_id,
        event.item_id,
    }
    assert (
        hydrated[context_note.version_id].version.context_note_identity.note_key
        == "team-to-beat"
    )
    with database_engine.connect() as connection:
        for table, version_id in (
            (EventVersion, event.version_id),
            (FactVersion, fact.version_id),
            (StorylineVersion, storyline.version_id),
            (TriggerVersion, trigger.version_id),
            (ContextNoteVersion, context_note.version_id),
        ):
            assert connection.scalar(
                sa.select(sa.func.count()).select_from(table).where(
                    table.version_id == version_id
                )
            ) == 1


def test_replace_retires_exact_visible_version_and_advances_once(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    create_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    create = CreateItem(client_key="record", content=_fact("Rockets are 6-2"))
    first = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=create_generation,
            operations=(create,),
        )
    )
    assert isinstance(first, RevisionCommitted)
    replace_generation = _generation(database_engine, domain, first.revision.id)

    replace_bundle = MemoryMutationBundle(
        producing_generation_id=replace_generation,
        operations=(
            ReplaceItem(
                item_id=create.item_id,
                content=_fact("Rockets are 7-2"),
                change_reason="Week 9 win",
            ),
        ),
    )
    second = _manager(database_engine).apply(replace_bundle)
    retry = _manager(database_engine).apply(replace_bundle)

    assert isinstance(second, RevisionCommitted)
    assert second.revision.sequence_number == 2
    assert second.items[0].version_id != create.version_id
    assert second.items[0].client_key is None
    assert retry == second
    history = _manager(database_engine).item_history(
        domain.competition_id, create.item_id
    )
    assert [version.revision_number for version in history.versions] == [1, 2]
    assert history.versions[0].retired_revision_id == second.revision.id
    assert history.versions[1].content.claim == "Rockets are 7-2"


def test_empty_and_identical_bundles_are_no_ops(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    empty_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    manager = _manager(database_engine)

    empty = manager.apply(
        MemoryMutationBundle(producing_generation_id=empty_generation)
    )
    assert isinstance(empty, NoChange)
    assert empty.revision.id == domain.root_revision_id

    create_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    create = CreateItem(client_key="record", content=_fact("Rockets are 6-2"))
    committed = manager.apply(
        MemoryMutationBundle(
            producing_generation_id=create_generation,
            operations=(create,),
        )
    )
    assert isinstance(committed, RevisionCommitted)
    identical_generation = _generation(
        database_engine, domain, committed.revision.id
    )
    identical = manager.apply(
        MemoryMutationBundle(
            producing_generation_id=identical_generation,
            operations=(
                ReplaceItem(item_id=create.item_id, content=create.content),
            ),
        )
    )

    assert isinstance(identical, NoChange)
    assert identical.revision.id == committed.revision.id
    with database_engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(MemoryRevision).where(
                MemoryRevision.competition_id == domain.competition_id
            )
        ) == 2


def test_retry_returns_the_existing_generation_revision(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    generation_id = _generation(
        database_engine, domain, domain.root_revision_id
    )
    create = CreateItem(client_key="record", content=_fact("Rockets are 6-2"))
    bundle = MemoryMutationBundle(
        producing_generation_id=generation_id,
        operations=(create,),
    )
    manager = _manager(database_engine)

    first = manager.apply(bundle)
    retry = manager.apply(bundle)

    assert isinstance(first, RevisionCommitted)
    assert retry == first
    with database_engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(MemoryRevision).where(
                MemoryRevision.producing_generation_id == generation_id
            )
        ) == 1


def test_stale_writer_fails_only_when_a_write_remains(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    first_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    stale_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    create = CreateItem(client_key="record", content=_fact("Rockets are 6-2"))
    committed = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=first_generation,
            operations=(create,),
        )
    )
    assert isinstance(committed, RevisionCommitted)

    with pytest.raises(StaleCanonicalRevision):
        _manager(database_engine).apply(
            MemoryMutationBundle(
                producing_generation_id=stale_generation,
                operations=(
                    CreateItem(client_key="other", content=_fact("Owls are 5-3")),
                ),
            )
        )



def test_stale_empty_returns_no_change_at_the_pinned_base(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    stale_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    advancing_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    advanced = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=advancing_generation,
            operations=(CreateItem(client_key="record", content=_fact("6-2")),),
        )
    )
    assert isinstance(advanced, RevisionCommitted)

    result = _manager(database_engine).apply(
        MemoryMutationBundle(producing_generation_id=stale_generation)
    )

    assert isinstance(result, NoChange)
    assert result.revision.id == domain.root_revision_id


def test_stale_identical_to_base_returns_no_change_at_the_pinned_base(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    create_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    create = CreateItem(client_key="record", content=_fact("Rockets are 6-2"))
    base = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=create_generation,
            operations=(create,),
        )
    )
    assert isinstance(base, RevisionCommitted)
    stale_generation = _generation(database_engine, domain, base.revision.id)
    advancing_generation = _generation(database_engine, domain, base.revision.id)
    advanced = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=advancing_generation,
            operations=(CreateItem(client_key="other", content=_fact("Owls 5-3")),),
        )
    )
    assert isinstance(advanced, RevisionCommitted)

    result = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=stale_generation,
            operations=(ReplaceItem(item_id=create.item_id, content=create.content),),
        )
    )

    assert isinstance(result, NoChange)
    assert result.revision.id == base.revision.id


def test_stale_already_applied_replace_and_create_return_current_no_change(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    create_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    original = CreateItem(client_key="record", content=_fact("Rockets are 6-2"))
    base = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=create_generation,
            operations=(original,),
        )
    )
    assert isinstance(base, RevisionCommitted)
    stale_replace_generation = _generation(database_engine, domain, base.revision.id)
    applying_generation = _generation(database_engine, domain, base.revision.id)
    desired = ReplaceItem(
        item_id=original.item_id,
        content=_fact("Rockets are 7-2"),
    )
    applied = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=applying_generation,
            operations=(desired,),
        )
    )
    assert isinstance(applied, RevisionCommitted)

    represented_replace = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=stale_replace_generation,
            operations=(desired,),
        )
    )
    assert isinstance(represented_replace, NoChange)
    assert represented_replace.revision.id == applied.revision.id

    other_domain = _seed_domain(database_engine)
    stale_create_generation = _generation(
        database_engine, other_domain, other_domain.root_revision_id
    )
    applying_create_generation = _generation(
        database_engine, other_domain, other_domain.root_revision_id
    )
    fixed_create = CreateItem(client_key="fixed", content=_fact("Fixed create"))
    created = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=applying_create_generation,
            operations=(fixed_create,),
        )
    )
    assert isinstance(created, RevisionCommitted)
    represented_create = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=stale_create_generation,
            operations=(fixed_create,),
        )
    )
    assert isinstance(represented_create, NoChange)
    assert represented_create.revision.id == created.revision.id


def test_stale_comparison_keeps_only_transitions_that_survived_pinned_base(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    create_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    first = CreateItem(client_key="first", content=_fact("A at base"))
    second = CreateItem(client_key="second", content=_fact("B at base"))
    base = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=create_generation,
            operations=(first, second),
        )
    )
    assert isinstance(base, RevisionCommitted)
    stale_generation = _generation(database_engine, domain, base.revision.id)
    applying_generation = _generation(database_engine, domain, base.revision.id)
    desired_second = _fact("B desired")
    advanced = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=applying_generation,
            operations=(
                ReplaceItem(item_id=first.item_id, content=_fact("A diverged")),
                ReplaceItem(item_id=second.item_id, content=desired_second),
            ),
        )
    )
    assert isinstance(advanced, RevisionCommitted)

    result = _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=stale_generation,
            operations=(
                ReplaceItem(item_id=first.item_id, content=first.content),
                ReplaceItem(item_id=second.item_id, content=desired_second),
            ),
        )
    )

    assert isinstance(result, NoChange)
    assert result.revision.id == advanced.revision.id


def test_rejects_duplicate_and_cross_scope_references(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    other = _seed_domain(database_engine)
    other_generation = _generation(
        database_engine, other, other.root_revision_id
    )
    other_fact = CreateItem(client_key="other-fact", content=_fact("Owls are 5-3"))
    _manager(database_engine).apply(
        MemoryMutationBundle(
            producing_generation_id=other_generation,
            operations=(other_fact,),
        )
    )
    generation_id = _generation(
        database_engine, domain, domain.root_revision_id
    )

    with pytest.raises(MemoryScopeViolation):
        _manager(database_engine).apply(
            MemoryMutationBundle(
                producing_generation_id=generation_id,
                operations=(
                    CreateItem(
                        client_key="arc",
                        content=StorylineContent(
                            headline="Foreign evidence",
                            summary="This should not cross leagues.",
                            status=StorylineStatus.ACTIVE,
                            salience=2,
                            evidence=(
                                EvidenceRef(
                                    kind="fact",
                                    version_id=other_fact.version_id,
                                    role="support",
                                ),
                            ),
                        ),
                    ),
                ),
            )
        )

    duplicate_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    with pytest.raises(InvalidMemoryReference, match="duplicate client key"):
        _manager(database_engine).apply(
            MemoryMutationBundle(
                producing_generation_id=duplicate_generation,
                operations=(
                    CreateItem(client_key="same", content=_fact("One")),
                    CreateItem(client_key="same", content=_fact("Two")),
                ),
            )
        )


def test_rejects_missing_player_and_source_receipt_before_persistence(
    database_engine: Engine,
) -> None:
    domain = _seed_domain(database_engine)
    player_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    with pytest.raises(InvalidMemoryReference, match="Sleeper player"):
        _manager(database_engine).apply(
            MemoryMutationBundle(
                producing_generation_id=player_generation,
                operations=(
                    CreateItem(
                        client_key="unknown-player",
                        content=FactContent(
                            claim="Unknown player scored twice",
                            category="performance",
                            confidence=MemoryConfidence.INFERRED,
                            status=FactStatus.ACTIVE,
                            subjects=(
                                PlayerRef(
                                    role="subject",
                                    id="missing-player",
                                ),
                            ),
                        ),
                    ),
                ),
            )
        )

    receipt_generation = _generation(
        database_engine, domain, domain.root_revision_id
    )
    with pytest.raises(InvalidMemoryReference, match="tool-call receipt"):
        _manager(database_engine).apply(
            MemoryMutationBundle(
                producing_generation_id=receipt_generation,
                operations=(
                    CreateItem(
                        client_key="missing-receipt",
                        content=FactContent(
                            claim="Rockets are 6-2",
                            category="record",
                            confidence=MemoryConfidence.SOURCE_BACKED,
                            status=FactStatus.ACTIVE,
                            primary_tool_call_id=uuid4(),
                        ),
                    ),
                ),
            )
        )


def test_stored_state_hash_mismatch_rolls_back_before_pointer_advance(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = _seed_domain(database_engine)
    generation_id = _generation(
        database_engine, domain, domain.root_revision_id
    )
    create = CreateItem(client_key="record", content=_fact("Rockets are 6-2"))
    monkeypatch.setattr(
        "backend.resources.memory.manager._resulting_state_hash",
        lambda *_args: "incorrect-state-hash",
    )

    with pytest.raises(CanonicalStateHashMismatch, match="resulting-state hash"):
        _manager(database_engine).apply(
            MemoryMutationBundle(
                producing_generation_id=generation_id,
                operations=(create,),
            )
        )

    with database_engine.connect() as connection:
        assert connection.scalar(
            sa.select(CurrentRevision.current_revision_id).where(
                CurrentRevision.competition_id == domain.competition_id
            )
        ) == domain.root_revision_id
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(MemoryItem).where(
                MemoryItem.id == create.item_id
            )
        ) == 0


def test_projection_failure_rolls_back_canonical_rows_and_pointer(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = _seed_domain(database_engine)
    generation_id = _generation(
        database_engine, domain, domain.root_revision_id
    )
    create = CreateItem(client_key="record", content=_fact("Rockets are 6-2"))

    def fail_projection(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("projection persistence failed")

    monkeypatch.setattr(
        "backend.resources.memory.manager._persist_search_documents",
        fail_projection,
    )
    with pytest.raises(RuntimeError, match="projection persistence failed"):
        _manager(database_engine).apply(
            MemoryMutationBundle(
                producing_generation_id=generation_id,
                operations=(create,),
            )
        )

    with database_engine.connect() as connection:
        assert connection.scalar(
            sa.select(CurrentRevision.current_revision_id).where(
                CurrentRevision.competition_id == domain.competition_id
            )
        ) == domain.root_revision_id
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(MemoryItem).where(
                MemoryItem.id == create.item_id
            )
        ) == 0
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(MemoryVersion).where(
                MemoryVersion.id == create.version_id
            )
        ) == 0
        assert connection.scalar(
            sa.select(sa.func.count()).select_from(MemoryRevision).where(
                MemoryRevision.producing_generation_id == generation_id
            )
        ) == 0
