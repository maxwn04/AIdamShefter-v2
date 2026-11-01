"""PostgreSQL commit, concurrent parent lock, legacy identity and as-of tests."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa

from backend.database.models.memory import MemoryItem
from backend.resources.memory.common.errors import StaleCanonicalRevisionError, RevisionNotFoundError
from backend.resources.memory.events.source_identity import SleeperTradeIdentity
from backend.services.memory import GenerationMemoryContext, MemoryRetrievalResult
from backend.services.memory.retrieval_service import MemoryRetrievalService
from backend.services.reporter.runner.tools import memory_tools
from backend.services.reporter.runner.tools.memory_event_evidence import ResolvedEvent
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.resources.memory.test_event_manager import _manager
from backend.tests.services.memory.test_mutation_service import _seed_domain, _service, _add_generation
from backend.tests.services.reporter.test_memory_tools import _registered, _call, FrozenData


class IdentityRetrieval(MemoryRetrievalService):
    def search(self, *, competition_id, revision_id, request):
        return MemoryRetrievalResult(competition_id=competition_id, revision_id=revision_id, matches=())


def setup_identity(engine, domain, pin, monkeypatch, *, transaction="tx-a", league="synthetic-league", provider="sleeper"):
    from types import SimpleNamespace
    manager = _manager(engine, domain.competition_id)
    retrieval = IdentityRetrieval(search_documents=SimpleNamespace(competition_id=domain.competition_id),
        events=manager, facts=None, storylines=None, triggers=None, context_notes=None)
    memory = GenerationMemoryContext(competition_id=domain.competition_id,
        generation_id=_add_generation(engine, domain), pinned_revision_id=pin,
        retrieval=retrieval, competition_season_id=domain.season_id, week=7)
    registry, context, *_ = _registered()
    adapter = memory_tools.register_memory_tools(registry, memory, FrozenData())
    hints = {"provider": provider, "league_id": league, "transaction_id": transaction,
             "competition_season_id": str(domain.season_id), "resolution_queries": []}
    resolved = ResolvedEvent({"kind": "trade", "assets": [{"kind": "draft_pick", "season": 2027,
        "round": 1, "original_franchise_id": str(domain.winner_id),
        "from_franchise_id": str(domain.winner_id), "to_franchise_id": str(domain.loser_id)}]}, 2, hints)
    monkeypatch.setattr(memory_tools, "resolve_event", lambda *a, **k: resolved)
    return registry, memory, manager, adapter


def save(registry, label, summary="A first-round pick changed teams."):
    result = _call(registry, "save_memory_event", id=label, event_type="trade", source_fact_ids=["synthetic-fact"],
                  headline="An exact source transaction", summary=summary)
    assert result.get("ok"), result
    return result


def test_source_identity_commits_one_item_retains_history_and_obeys_pin_and_scope(database_engine, monkeypatch):
    d = _seed_domain(database_engine);service = _service(database_engine, d)
    r, m, manager, _ = setup_identity(database_engine, d, d.root_revision_id, monkeypatch)
    save(r, "first-label")
    bundle = m.take_completed_bundle();proposal = bundle.proposals[0]
    legacy_hints = {"transaction_id": "tx-a", "competition_season_id": str(d.season_id),
                    "resolution_queries": [{"parameters": {"league": "synthetic-league"}}]}
    proposal = proposal.model_copy(update={"metadata": proposal.metadata.model_copy(update={"agent_key": "legacy-label"}),
        "content": proposal.content.model_copy(update={"source_hints": legacy_hints})})
    first = service.apply(bundle.model_copy(update={"proposals": (proposal,)}))
    identity = SleeperTradeIdentity(d.season_id, "synthetic-league", "tx-a")
    old = manager.trade_at_source(identity, first.revision.revision_id, through_week=7)[0]
    r, m, _, a = setup_identity(database_engine, d, first.revision.revision_id, monkeypatch)
    save(r, "another-label", "A later source-backed assessment, retained as a new version.")
    assert m.proposal_snapshot()[0].item_id == old.item.item_id
    second = service.apply(m.take_completed_bundle())
    current = manager.trade_at_source(identity, second.revision.revision_id, through_week=7)[0]
    assert current.item.item_id == old.item.item_id and current.item.agent_key == "legacy-label"
    assert current.version.revision_number == 2
    assert manager.trade_at_source(identity, first.revision.revision_id, through_week=7)[0].content.summary == old.content.summary
    assert manager.trade_at_source(identity, d.root_revision_id, through_week=7) == ()
    assert manager.trade_at_source(identity, second.revision.revision_id, through_week=1) == ()
    assert len(manager.history(old.item.item_id)) == 2
    assert manager.trade_at_source(SleeperTradeIdentity(d.season_id, "other-league", "tx-a"), second.revision.revision_id, through_week=7) == ()
    assert manager.trade_at_source(SleeperTradeIdentity(uuid4(), "synthetic-league", "tx-a"), second.revision.revision_id, through_week=7) == ()
    other = _seed_domain(database_engine)
    assert _manager(database_engine, other.competition_id).trade_at_source(identity, second.revision.revision_id, through_week=7) == ()


def test_two_concurrent_generations_cannot_commit_duplicate_then_fresh_retry_reuses_identity(database_engine, monkeypatch):
    d = _seed_domain(database_engine);service = _service(database_engine, d)
    r1, m1, manager, _ = setup_identity(database_engine, d, d.root_revision_id, monkeypatch)
    r2, m2, _, _ = setup_identity(database_engine, d, d.root_revision_id, monkeypatch)
    save(r1, "writer-one");save(r2, "writer-two")
    bundles = [m1.take_completed_bundle(), m2.take_completed_bundle()];barrier = Barrier(2)
    def commit(bundle):
        barrier.wait(timeout=10)
        try:return service.apply(bundle)
        # The existing joined FOR UPDATE can surface RevisionNotFoundError on
        # its read-committed recheck. Both abort; identity safety is the assertion.
        except (StaleCanonicalRevisionError, RevisionNotFoundError) as error:
            return type(error).__name__
    with ThreadPoolExecutor(max_workers=2) as pool:results = list(pool.map(commit, bundles))
    assert sum(isinstance(x, str) for x in results) == 1
    committed = next(x for x in results if not isinstance(x, str))
    identity = SleeperTradeIdentity(d.season_id, "synthetic-league", "tx-a")
    rows = manager.trade_at_source(identity, committed.revision.revision_id, through_week=7)
    assert len(rows) == 1
    r, m, _, _ = setup_identity(database_engine, d, committed.revision.revision_id, monkeypatch)
    save(r, "retry-label", "Later assessment after reloading the winning pin.")
    assert m.proposal_snapshot()[0].operation == "replace" and m.proposal_snapshot()[0].item_id == rows[0].item.item_id
    service.apply(m.take_completed_bundle())
    with database_engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(MemoryItem).where(MemoryItem.competition_id == d.competition_id)) == 1


def test_same_transaction_text_in_other_league_is_distinct(database_engine, monkeypatch):
    d = _seed_domain(database_engine);service = _service(database_engine, d)
    r, m, manager, _ = setup_identity(database_engine, d, d.root_revision_id, monkeypatch)
    save(r, "league-one");first = service.apply(m.take_completed_bundle())
    r, m, _, _ = setup_identity(database_engine, d, first.revision.revision_id, monkeypatch, league="another-league")
    save(r, "league-two");second = service.apply(m.take_completed_bundle())
    one = manager.trade_at_source(SleeperTradeIdentity(d.season_id, "synthetic-league", "tx-a"), second.revision.revision_id, through_week=7)
    two = manager.trade_at_source(SleeperTradeIdentity(d.season_id, "another-league", "tx-a"), second.revision.revision_id, through_week=7)
    assert len(one) == len(two) == 1 and one[0].item.item_id != two[0].item.item_id
