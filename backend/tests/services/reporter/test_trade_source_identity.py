"""Synthetic source-driven identity regressions; no provider calls or private data."""
from uuid import uuid4

import pytest

from backend.resources.memory.events.source_identity import SleeperTradeIdentity
from backend.services.memory import HydratedMemoryMatch, MemoryKind
from backend.tests.services.reporter.test_memory_tools import _call, _event_match, SEASON_ID
from backend.tests.services.reporter.test_memory_evidence_handoff import setup, saved_source_fact


def prepared(matches=(), *, transaction="trade1"):
    registry, context, memory, retrieval, adapter, data = setup(matches)
    data.add_trade(player_id="synthetic-player-1", player_name="Example Receiver")
    if transaction != "trade1":
        data.connection.execute("UPDATE transactions SET transaction_id=?", (transaction,))
        data.connection.execute("UPDATE transaction_moves SET transaction_id=?", (transaction,))
    saved_source_fact(registry, context, "transactions", week_from=2, week_to=2)
    return registry, context, memory, adapter


def args(label="local-trade", **changes):
    return dict(id=label, event_type="trade", source_fact_ids=["fact_event"],
                headline="Two clubs exchange assets", summary="A receiver moved for picks.", **changes)


def prior(proposal, *, key="legacy-model-label", status="active"):
    template = _event_match()
    memory = template.memory.model_copy(update={
        "item": template.memory.item.model_copy(update={"item_id": proposal.item_id, "agent_key": key}),
        "version": template.memory.version.model_copy(update={"version_id": proposal.version_id,
            "competition_season_id": SEASON_ID, "week": 2, "revision_number": 1}),
        "content": type(proposal.content).model_validate({**proposal.content.model_dump(), "status": status}),
    })
    # Validate copies so enum status behaves exactly like hydrated canonical data.
    memory = type(template.memory).model_validate(memory.model_dump())
    return HydratedMemoryMatch.model_validate({**template.model_dump(), "memory": memory})


def test_different_labels_and_tool_receipts_reuse_one_proposal_and_linkable_version():
    r, c, m, a = prepared()
    with c.bind_tool_execution(uuid4()):
        first = _call(r, "save_memory_event", **args("first-label"))
    with c.bind_tool_execution(uuid4()):
        retry = _call(r, "save_memory_event", **args("another-label"))
    assert first["saved"] and retry["no_change"] and not retry["saved"]
    assert len(m.proposal_snapshot()) == 1
    assert a._agent_reference(MemoryKind.EVENT, "first-label") == a._agent_reference(MemoryKind.EVENT, "another-label")
    assert m.proposal_snapshot()[0].metadata.agent_key.startswith("source-trade:")


def test_conflicting_same_run_claim_fails_without_a_second_identity():
    r, c, m, a = prepared()
    _call(r, "save_memory_event", **args())
    changed = {**args("another-label"), "summary": "A materially different claim."}
    result = _call(r, "save_memory_event", **changed)
    assert result["error"]["code"] == "memory_already_selected"
    assert len(m.proposal_snapshot()) == 1
    assert (MemoryKind.EVENT, "another-label") not in a._local_agent_refs


def test_new_generation_updates_legacy_identity_and_preserves_old_reference():
    r, c, m, a = prepared();_call(r, "save_memory_event", **args())
    original = m.proposal_snapshot()[0];old = prior(original)
    r, c, m, a = prepared((old,))
    result = _call(r, "save_memory_event", **{**args("new-label"), "summary": "An evidence-supported later assessment."})
    p = m.proposal_snapshot()[0]
    assert result["saved"] and p.operation == "replace"
    assert p.item_id == original.item_id and p.expected_item_revision == 1
    assert p.metadata.agent_key is None
    assert a._agent_reference(MemoryKind.EVENT, "legacy-model-label").version_id == p.version_id
    assert old.memory.content.summary == "A receiver moved for picks."


def test_identical_assets_in_distinct_transactions_stay_distinct_and_alias_cannot_overwrite():
    r, c, m, a = prepared();_call(r, "save_memory_event", **args())
    original = m.proposal_snapshot()[0];old = prior(original)
    r, c, m, a = prepared((old,), transaction="trade2")
    conflict = _call(r, "save_memory_event", **args("legacy-model-label"))
    assert conflict["error"]["code"] == "event_alias_conflict"
    assert not m.proposal_snapshot()
    result = _call(r, "save_memory_event", **args("distinct-trade"))
    p = m.proposal_snapshot()[0]
    assert result["saved"] and p.operation == "create" and p.item_id != original.item_id


def test_existing_duplicate_source_cards_fail_closed_without_merging():
    r, c, m, a = prepared();_call(r, "save_memory_event", **args())
    p = m.proposal_snapshot()[0];one = prior(p)
    two = prior(p.model_copy(update={"item_id": uuid4(), "version_id": uuid4()}), key="another-old-key")
    r, c, m, a = prepared((one, two))
    result = _call(r, "save_memory_event", **args("new-label"))
    assert result["error"]["code"] == "duplicate_trade_identity"
    assert not m.proposal_snapshot()


def test_inactive_source_event_is_not_reactivated():
    r, c, m, a = prepared();_call(r, "save_memory_event", **args())
    old = prior(m.proposal_snapshot()[0], status="archived")
    r, c, m, a = prepared((old,))
    result = _call(r, "save_memory_event", **args("new-label"))
    assert result["error"]["code"] == "inactive_trade_identity"
    assert not m.proposal_snapshot()


def test_failed_call_savepoint_restores_alias_and_source_selection():
    r, c, m, a = prepared()
    with pytest.raises(RuntimeError), a.write_savepoint():
        _call(r, "save_memory_event", **args())
        raise RuntimeError("injected failure before committing tool state")
    assert not m.proposal_snapshot() and not a._trade_selections and not a._local_agent_refs
    assert _call(r, "save_memory_event", **args("retry"))["saved"]


def test_identity_separates_league_season_transaction_and_rejects_other_provider():
    base = SleeperTradeIdentity(SEASON_ID, "league-a", "transaction-a")
    assert len({x.agent_key for x in [base, SleeperTradeIdentity(SEASON_ID, "league-b", "transaction-a"),
        SleeperTradeIdentity(uuid4(), "league-a", "transaction-a"),
        SleeperTradeIdentity(SEASON_ID, "league-a", "transaction-b")]}) == 4
    with pytest.raises(ValueError, match="not a Sleeper"):
        SleeperTradeIdentity.from_hints({"provider": "another-provider"}, SEASON_ID)
