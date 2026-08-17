from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.memory import MemorySearchDocument
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common import SearchProjectionHydrationError
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.context_notes import ContextNoteManager
from backend.resources.memory.events import Event, EventManager, MatchupEventPayload
from backend.resources.memory.facts import FactManager
from backend.resources.memory.search_documents import (
    SearchDocumentManager,
    SearchDocumentQuery,
)
from backend.resources.memory.storylines import (
    RelatedStorylineRef,
    RelatedStorylineRole,
    StorylineContent,
    StorylineManager,
)
from backend.resources.memory.triggers import TriggerManager
from backend.services.memory import (
    FactOriginatingEventExpansion,
    MemoryMutationOrigin,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    MemoryRetrievalService,
    RelatedStorylineExpansion,
    StorylineEvidenceExpansion,
    TriggerOriginEventExpansion,
    TriggerTargetStorylineExpansion,
)
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.services.memory.test_mutation_service import (
    Domain,
    _add_generation,
    _complete_bundle,
    _event,
    _fact,
    _seed_domain,
    _service,
    _storyline,
)


def _manager_context(domain: Domain) -> ManagerContext[CompetitionScope]:
    return ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "system_process", "process_name": "retrieval-test"},
            "scope": {
                "kind": "competition",
                "competition_id": domain.competition_id,
            },
            "correlation_id": uuid4(),
        }
    )


def _retrieval_service(
    engine: Engine,
    domain: Domain,
) -> tuple[MemoryRetrievalService, SearchDocumentManager]:
    sessions = create_session_factory(engine)
    context = _manager_context(domain)
    search = SearchDocumentManager(sessions, context)
    return (
        MemoryRetrievalService(
            search_documents=search,
            facts=FactManager(sessions, context),
            events=EventManager(sessions, context),
            storylines=StorylineManager(sessions, context),
            triggers=TriggerManager(sessions, context),
            context_notes=ContextNoteManager(sessions, context),
        ),
        search,
    )


def _committed_bundle(
    engine: Engine,
) -> tuple[Domain, dict[str, UUID], UUID]:
    domain = _seed_domain(engine)
    bundle, ids = _complete_bundle(domain)
    result = _service(engine, domain).apply(bundle)
    assert result.revision is not None
    return domain, ids, result.revision.revision_id


def test_search_hydrates_all_kinds_and_expands_typed_references(
    database_engine: Engine,
) -> None:
    domain, ids, revision_id = _committed_bundle(database_engine)
    service, search = _retrieval_service(database_engine, domain)
    query = SearchDocumentQuery(
        entity_keys=(f"franchise:{domain.winner_id}",),
        evidence_version_ids=(ids["fact_version"],),
        related_item_ids=(ids["event_item"],),
        tags=("playoffs",),
        text="volatile playoff race",
    )

    candidates = search.search(revision_id, query)
    result = service.search(
        competition_id=domain.competition_id,
        revision_id=revision_id,
        request=MemoryRetrievalRequest(
            query=query,
            expand_exact_references=True,
            expand_stable_references=True,
        ),
    )

    assert [match.memory.version.version_id for match in result.matches] == [
        candidate.version_id for candidate in candidates
    ]
    assert [match.score for match in result.matches] == [
        candidate.score for candidate in candidates
    ]
    by_kind = {match.memory.item.kind: match for match in result.matches}
    assert set(by_kind) == set(MemoryKind)
    event = cast(Event, by_kind[MemoryKind.EVENT].memory)
    assert isinstance(event.content.details, MatchupEventPayload)
    assert event.content.details.kind == "matchup"
    assert event.content.details.sleeper_matchup_id == "week-7-main"
    assert by_kind[MemoryKind.EVENT].matched_entity_keys == (
        f"franchise:{domain.winner_id}",
    )

    fact_exact = by_kind[MemoryKind.FACT].exact_references
    assert len(fact_exact) == 1
    assert isinstance(fact_exact[0], FactOriginatingEventExpansion)
    assert fact_exact[0].memory.version.version_id == ids["event_version"]

    storyline_exact = by_kind[MemoryKind.STORYLINE].exact_references
    assert all(
        isinstance(expansion, StorylineEvidenceExpansion)
        for expansion in storyline_exact
    )
    assert {
        (expansion.reference.role.value, expansion.memory.version.version_id)
        for expansion in storyline_exact
        if isinstance(expansion, StorylineEvidenceExpansion)
    } == {
        ("origin", ids["event_version"]),
        ("support", ids["fact_version"]),
    }

    trigger_stable = by_kind[MemoryKind.TRIGGER].stable_references
    assert isinstance(trigger_stable[0], TriggerTargetStorylineExpansion)
    assert isinstance(trigger_stable[1], TriggerOriginEventExpansion)
    assert trigger_stable[0].memory.version.version_id == ids["storyline_version"]
    assert trigger_stable[1].memory.version.version_id == ids["event_version"]
    assert "note_identity" in by_kind[MemoryKind.CONTEXT_NOTE].memory.model_dump()

    dumped_match = by_kind[MemoryKind.EVENT].model_dump()
    assert "candidate" not in dumped_match
    serialized = result.model_dump_json()
    for derived_field in (
        "document_text",
        "content_hash",
        "builder_version",
        "search_vector",
        "indexed_at",
    ):
        assert f'"{derived_field}"' not in serialized
    round_trip = MemoryRetrievalResult.model_validate_json(serialized)
    assert [match.memory.item.kind for match in round_trip.matches] == [
        match.memory.item.kind for match in result.matches
    ]


def test_exact_expansion_keeps_retired_evidence_and_search_stays_pinned(
    database_engine: Engine,
) -> None:
    domain, ids, first_revision_id = _committed_bundle(database_engine)
    generation_id = _add_generation(database_engine, domain)
    replaced = _service(database_engine, domain).replace_fact(
        MemoryMutationOrigin(
            generation_id=generation_id,
            expected_revision_id=first_revision_id,
            competition_season_id=domain.season_id,
            week=8,
        ),
        ids["fact_item"],
        1,
        _fact(domain, ids["event_version"], archived=True),
    )
    assert replaced.revision is not None
    second_revision_id = replaced.revision.revision_id
    replacement_version_id = replaced.changes[0].version_id
    service, _ = _retrieval_service(database_engine, domain)

    storyline_result = service.search(
        competition_id=domain.competition_id,
        revision_id=second_revision_id,
        request=MemoryRetrievalRequest(
            query=SearchDocumentQuery(
                evidence_version_ids=(ids["fact_version"],),
                kinds=(MemoryKind.STORYLINE,),
            ),
            expand_exact_references=True,
        ),
    )
    evidence_versions = {
        expansion.memory.version.version_id
        for expansion in storyline_result.matches[0].exact_references
        if isinstance(expansion, StorylineEvidenceExpansion)
    }
    assert ids["fact_version"] in evidence_versions
    assert replacement_version_id not in evidence_versions

    fact_query = SearchDocumentQuery(
        entity_keys=(f"franchise:{domain.winner_id}",),
        kinds=(MemoryKind.FACT,),
    )
    before = service.search(
        competition_id=domain.competition_id,
        revision_id=first_revision_id,
        request=MemoryRetrievalRequest(query=fact_query),
    )
    after = service.search(
        competition_id=domain.competition_id,
        revision_id=second_revision_id,
        request=MemoryRetrievalRequest(
            query=fact_query,
            expand_exact_references=True,
        ),
    )
    assert before.matches[0].memory.version.version_id == ids["fact_version"]
    assert after.matches[0].memory.version.version_id == replacement_version_id
    assert isinstance(
        after.matches[0].exact_references[0],
        FactOriginatingEventExpansion,
    )


def test_stable_trigger_references_follow_the_pinned_revision(
    database_engine: Engine,
) -> None:
    domain, ids, first_revision_id = _committed_bundle(database_engine)
    event_generation_id = _add_generation(database_engine, domain)
    event_content = _event(domain).model_copy(
        update={"headline": "The rematch confirmed the result."}
    )
    replaced_event = _service(database_engine, domain).replace_event(
        MemoryMutationOrigin(
            generation_id=event_generation_id,
            expected_revision_id=first_revision_id,
            competition_season_id=domain.season_id,
            week=8,
        ),
        ids["event_item"],
        1,
        event_content,
    )
    assert replaced_event.revision is not None
    storyline_generation_id = _add_generation(database_engine, domain)
    storyline_content = _storyline(
        domain,
        ids["event_version"],
        ids["fact_version"],
    ).model_copy(update={"headline": "The playoff path stayed open"})
    replaced_storyline = _service(database_engine, domain).replace_storyline(
        MemoryMutationOrigin(
            generation_id=storyline_generation_id,
            expected_revision_id=replaced_event.revision.revision_id,
            competition_season_id=domain.season_id,
            week=9,
        ),
        ids["storyline_item"],
        1,
        storyline_content,
    )
    assert replaced_storyline.revision is not None
    latest_revision_id = replaced_storyline.revision.revision_id
    service, _ = _retrieval_service(database_engine, domain)
    request = MemoryRetrievalRequest(
        query=SearchDocumentQuery(kinds=(MemoryKind.TRIGGER,)),
        expand_stable_references=True,
    )

    before = service.search(
        competition_id=domain.competition_id,
        revision_id=first_revision_id,
        request=request,
    )
    after = service.search(
        competition_id=domain.competition_id,
        revision_id=latest_revision_id,
        request=request,
    )

    before_targets = {
        expansion.kind: expansion.memory.version.version_id
        for expansion in before.matches[0].stable_references
    }
    after_targets = {
        expansion.kind: expansion.memory.version.version_id
        for expansion in after.matches[0].stable_references
    }
    assert before_targets == {
        "trigger_target_storyline": ids["storyline_version"],
        "trigger_origin_event": ids["event_version"],
    }
    assert after_targets == {
        "trigger_target_storyline": replaced_storyline.changes[0].version_id,
        "trigger_origin_event": replaced_event.changes[0].version_id,
    }


def test_related_storyline_expansion_is_one_hop_and_revision_visible(
    database_engine: Engine,
) -> None:
    domain, ids, first_revision_id = _committed_bundle(database_engine)
    related_generation_id = _add_generation(database_engine, domain)
    related_content = _storyline(
        domain,
        ids["event_version"],
        ids["fact_version"],
    ).model_copy(update={"headline": "A parallel playoff arc emerged"})
    related = _service(database_engine, domain).create_storyline(
        MemoryMutationOrigin(
            generation_id=related_generation_id,
            expected_revision_id=first_revision_id,
            competition_season_id=domain.season_id,
            week=8,
        ),
        related_content,
    )
    assert related.revision is not None
    related_item_id = related.changes[0].item_id
    owner_generation_id = _add_generation(database_engine, domain)
    owner_payload = _storyline(
        domain,
        ids["event_version"],
        ids["fact_version"],
    ).model_dump()
    owner_payload["related_storylines"] = [
        RelatedStorylineRef(
            item_id=related_item_id,
            role=RelatedStorylineRole.RELATED_ARC,
        ).model_dump()
    ]
    owner = _service(database_engine, domain).replace_storyline(
        MemoryMutationOrigin(
            generation_id=owner_generation_id,
            expected_revision_id=related.revision.revision_id,
            competition_season_id=domain.season_id,
            week=9,
        ),
        ids["storyline_item"],
        1,
        StorylineContent.model_validate(owner_payload),
    )
    assert owner.revision is not None
    owner_revision_id = owner.revision.revision_id
    replacement_generation_id = _add_generation(database_engine, domain)
    related_replacement = _service(database_engine, domain).replace_storyline(
        MemoryMutationOrigin(
            generation_id=replacement_generation_id,
            expected_revision_id=owner_revision_id,
            competition_season_id=domain.season_id,
            week=10,
        ),
        related_item_id,
        1,
        related_content.model_copy(
            update={"headline": "The parallel arc changed direction"}
        ),
    )
    assert related_replacement.revision is not None
    service, _ = _retrieval_service(database_engine, domain)
    request = MemoryRetrievalRequest(
        query=SearchDocumentQuery(
            related_item_ids=(related_item_id,),
            kinds=(MemoryKind.STORYLINE,),
        ),
        expand_exact_references=True,
        expand_stable_references=True,
    )

    before = service.search(
        competition_id=domain.competition_id,
        revision_id=owner_revision_id,
        request=request,
    )
    after = service.search(
        competition_id=domain.competition_id,
        revision_id=related_replacement.revision.revision_id,
        request=request,
    )

    before_expansion = before.matches[0].stable_references[0]
    after_expansion = after.matches[0].stable_references[0]
    assert isinstance(before_expansion, RelatedStorylineExpansion)
    assert isinstance(after_expansion, RelatedStorylineExpansion)
    assert before_expansion.reference.role.value == "related_arc"
    assert before_expansion.memory.version.version_id == related.changes[0].version_id
    assert (
        after_expansion.memory.version.version_id
        == related_replacement.changes[0].version_id
    )
    assert not hasattr(before_expansion.memory, "stable_references")


@pytest.mark.parametrize("corrupt_field", ["kind", "item_id"])
def test_projection_identity_corruption_fails_the_complete_request(
    database_engine: Engine,
    corrupt_field: str,
) -> None:
    domain, ids, revision_id = _committed_bundle(database_engine)
    with database_engine.begin() as connection:
        value: str | UUID = "fact" if corrupt_field == "kind" else uuid4()
        connection.execute(
            sa.update(MemorySearchDocument)
            .where(MemorySearchDocument.version_id == ids["event_version"])
            .values({corrupt_field: value})
        )
    service, _ = _retrieval_service(database_engine, domain)

    with pytest.raises(SearchProjectionHydrationError) as raised:
        service.search(
            competition_id=domain.competition_id,
            revision_id=revision_id,
            request=MemoryRetrievalRequest(
                query=SearchDocumentQuery(text="one-point finish")
            ),
        )

    assert raised.value.version_id == ids["event_version"]


def test_expansion_defaults_off_and_scope_mismatch_is_rejected(
    database_engine: Engine,
) -> None:
    domain, _, revision_id = _committed_bundle(database_engine)
    service, _ = _retrieval_service(database_engine, domain)
    request = MemoryRetrievalRequest(
        query=SearchDocumentQuery(kinds=(MemoryKind.STORYLINE,))
    )

    result = service.search(
        competition_id=domain.competition_id,
        revision_id=revision_id,
        request=request,
    )

    assert result.matches[0].exact_references == ()
    assert result.matches[0].stable_references == ()
    with pytest.raises(ValueError, match="outside the service competition"):
        service.search(
            competition_id=uuid4(),
            revision_id=revision_id,
            request=request,
        )
