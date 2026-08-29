from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.memory import (
    CurrentRevision,
    MemoryRevision,
    MemorySearchDocument,
)
from backend.database.sessions import create_session_factory
from backend.resources.context import CompetitionScope, ManagerContext
from backend.resources.memory.common import RevisionNotFoundError
from backend.resources.memory.common.kinds import MemoryKind
from backend.resources.memory.search_documents import (
    SearchDocumentManager,
    SearchDocumentQuery,
    SearchMatchReason,
)
from backend.services.memory import MemoryMutationOrigin
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.services.memory.test_mutation_service import (
    Domain,
    _add_generation,
    _complete_bundle,
    _fact,
    _seed_domain,
    _service,
)


def _manager(engine: Engine, domain: Domain) -> SearchDocumentManager:
    context = ManagerContext[CompetitionScope].model_validate(
        {
            "actor": {"kind": "system_process", "process_name": "projection-test"},
            "scope": {
                "kind": "competition",
                "competition_id": domain.competition_id,
            },
            "correlation_id": uuid4(),
        }
    )
    return SearchDocumentManager(create_session_factory(engine), context)


def _committed_bundle(
    engine: Engine,
) -> tuple[Domain, dict[str, UUID], UUID]:
    domain = _seed_domain(engine)
    bundle, ids = _complete_bundle(domain)
    result = _service(engine, domain).apply(bundle)
    assert result.revision is not None
    return domain, ids, result.revision.revision_id


def test_search_combines_discovery_signals_filters_and_named_scores(
    database_engine: Engine,
) -> None:
    domain, ids, revision_id = _committed_bundle(database_engine)
    manager = _manager(database_engine, domain)

    candidates = manager.search(
        revision_id,
        SearchDocumentQuery(
            entity_keys=(f"franchise:{domain.winner_id}",),
            evidence_version_ids=(ids["fact_version"],),
            related_item_ids=(ids["event_item"],),
            tags=("PLAYOFFS",),
            text="volatile playoff race",
            statuses=("active", "open"),
            competition_season_id=domain.season_id,
            week=7,
        ),
    )

    by_kind = {candidate.kind: candidate for candidate in candidates}
    assert set(by_kind) == set(MemoryKind)
    assert by_kind[MemoryKind.EVENT].matched_entity_keys == (
        f"franchise:{domain.winner_id}",
    )
    assert by_kind[MemoryKind.STORYLINE].matched_evidence_version_ids == (
        ids["fact_version"],
    )
    assert by_kind[MemoryKind.TRIGGER].matched_related_item_ids == (
        ids["event_item"],
    )
    assert by_kind[MemoryKind.CONTEXT_NOTE].matched_tags == ("playoffs",)
    assert SearchMatchReason.ENTITY_OVERLAP in by_kind[MemoryKind.EVENT].match_reasons
    assert (
        SearchMatchReason.EVIDENCE_OVERLAP
        in by_kind[MemoryKind.STORYLINE].match_reasons
    )
    assert (
        SearchMatchReason.RELATED_ITEM_OVERLAP
        in by_kind[MemoryKind.TRIGGER].match_reasons
    )
    assert SearchMatchReason.TAG_OVERLAP in by_kind[MemoryKind.CONTEXT_NOTE].match_reasons
    assert any(
        SearchMatchReason.LEXICAL_MATCH in candidate.match_reasons
        for candidate in candidates
    )
    assert by_kind[MemoryKind.EVENT].score_components.salience == 0.5
    assert by_kind[MemoryKind.EVENT].score == pytest.approx(
        by_kind[MemoryKind.EVENT].score_components.total
    )
    assert "document_text" not in by_kind[MemoryKind.EVENT].model_dump()


def test_search_supports_filter_only_browsing_limits_and_scope(
    database_engine: Engine,
) -> None:
    domain, _, revision_id = _committed_bundle(database_engine)
    other = _seed_domain(database_engine)
    manager = _manager(database_engine, domain)

    candidates = manager.search(
        revision_id,
        SearchDocumentQuery(
            kinds=(MemoryKind.STORYLINE, MemoryKind.EVENT),
            statuses=("active",),
            limit=1,
        ),
    )

    assert len(candidates) == 1
    assert candidates[0].kind is MemoryKind.EVENT
    assert candidates[0].match_reasons == (SearchMatchReason.BROWSE_MATCH,)
    with pytest.raises(RevisionNotFoundError):
        manager.search(uuid4(), SearchDocumentQuery())
    with pytest.raises(RevisionNotFoundError):
        manager.search(other.root_revision_id, SearchDocumentQuery())


def test_search_supports_inclusive_week_ranges_and_exact_week_compatibility(
    database_engine: Engine,
) -> None:
    domain, _, revision_id = _committed_bundle(database_engine)
    manager = _manager(database_engine, domain)

    exact = manager.search(revision_id, SearchDocumentQuery(week=7))
    ranged = manager.search(
        revision_id,
        SearchDocumentQuery(week_from=7, week_to=7),
    )
    after = manager.search(revision_id, SearchDocumentQuery(week_from=8))

    assert exact
    assert [candidate.version_id for candidate in ranged] == [
        candidate.version_id for candidate in exact
    ]
    assert after == ()
    with pytest.raises(ValueError, match="week_from cannot be greater"):
        SearchDocumentQuery(week_from=8, week_to=7)
    with pytest.raises(ValueError, match="week cannot be combined"):
        SearchDocumentQuery(week=7, week_from=7)


def test_search_visibility_is_pinned_to_the_exact_revision(
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
    replacement_version_id = replaced.changes[0].version_id
    manager = _manager(database_engine, domain)
    query = SearchDocumentQuery(
        entity_keys=(f"franchise:{domain.winner_id}",),
        kinds=(MemoryKind.FACT,),
    )

    before = manager.search(first_revision_id, query)
    after = manager.search(replaced.revision.revision_id, query)

    assert [candidate.version_id for candidate in before] == [ids["fact_version"]]
    assert [candidate.version_id for candidate in after] == [replacement_version_id]
    assert before[0].status == "active"
    assert after[0].status == "archived"


def test_rebuild_restores_all_historical_documents_without_changing_history(
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
    manager = _manager(database_engine, domain)

    with database_engine.begin() as connection:
        revision_snapshot = connection.execute(
            sa.select(
                MemoryRevision.id,
                MemoryRevision.sequence_number,
                MemoryRevision.state_content_hash,
            )
            .where(MemoryRevision.competition_id == domain.competition_id)
            .order_by(MemoryRevision.sequence_number)
        ).all()
        current_snapshot = connection.execute(
            sa.select(
                CurrentRevision.current_revision_id,
                CurrentRevision.lock_version,
            ).where(CurrentRevision.competition_id == domain.competition_id)
        ).one()
        connection.execute(
            sa.delete(MemorySearchDocument).where(
                MemorySearchDocument.version_id == ids["event_version"]
            )
        )
        connection.execute(
            sa.update(MemorySearchDocument)
            .where(MemorySearchDocument.version_id == ids["storyline_version"])
            .values(document_text="corrupt projection", builder_version=99)
        )

    result = manager.rebuild()

    assert result.canonical_revision_id == replaced.revision.revision_id
    assert result.documents_rebuilt == 6
    with database_engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(MemorySearchDocument)
            .where(MemorySearchDocument.competition_id == domain.competition_id)
        ) == 6
        restored = connection.execute(
            sa.select(
                MemorySearchDocument.document_text,
                MemorySearchDocument.builder_version,
            ).where(
                MemorySearchDocument.version_id == ids["storyline_version"]
            )
        ).one()
        assert restored.builder_version == 1
        assert "Owls opened a playoff path" in restored.document_text
        assert connection.execute(
            sa.select(
                MemoryRevision.id,
                MemoryRevision.sequence_number,
                MemoryRevision.state_content_hash,
            )
            .where(MemoryRevision.competition_id == domain.competition_id)
            .order_by(MemoryRevision.sequence_number)
        ).all() == revision_snapshot
        assert connection.execute(
            sa.select(
                CurrentRevision.current_revision_id,
                CurrentRevision.lock_version,
            ).where(CurrentRevision.competition_id == domain.competition_id)
        ).one() == current_snapshot

    historical = manager.search(
        first_revision_id,
        SearchDocumentQuery(
            entity_keys=(f"franchise:{domain.winner_id}",),
            kinds=(MemoryKind.FACT,),
        ),
    )
    assert [candidate.version_id for candidate in historical] == [ids["fact_version"]]


def test_failed_rebuild_preserves_the_previous_projection(
    database_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain, _, _ = _committed_bundle(database_engine)
    manager = _manager(database_engine, domain)
    with database_engine.connect() as connection:
        before = connection.execute(
            sa.select(
                MemorySearchDocument.version_id,
                MemorySearchDocument.content_hash,
            )
            .where(MemorySearchDocument.competition_id == domain.competition_id)
            .order_by(MemorySearchDocument.version_id)
        ).all()

    def fail_decode(*_args: object) -> object:
        raise ValueError("unsupported fact content schema version 99")

    monkeypatch.setattr(
        "backend.resources.memory.search_documents.manager.decode_fact",
        fail_decode,
    )

    with pytest.raises(ValueError, match="unsupported fact content schema version"):
        manager.rebuild()

    with database_engine.connect() as connection:
        after = connection.execute(
            sa.select(
                MemorySearchDocument.version_id,
                MemorySearchDocument.content_hash,
            )
            .where(MemorySearchDocument.competition_id == domain.competition_id)
            .order_by(MemorySearchDocument.version_id)
        ).all()
    assert after == before
