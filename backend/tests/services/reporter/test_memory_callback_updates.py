"""Callback actions and storyline identity through the public memory adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.memory import MemoryVersion
from backend.resources.memory.storylines import StorylineContent
from backend.resources.memory.triggers import Trigger, TriggerContent
from backend.services.memory import GenerationMemoryContext, HydratedMemoryMatch, MemoryKind
from backend.services.reporter.runner.memory_closeout import MemoryCloseoutState
from backend.services.reporter.runner.tools.memory_closeout_tools import complete_memory_review
from backend.services.reporter.runner.tools.memory_tools import register_memory_tools
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.resources.memory.test_event_manager import _seed_domain, _trade
from backend.tests.services.memory.test_mutation_service import (
    _add_generation, _generation_context, _service,
)
from backend.tests.services.memory.test_retrieval_service import _retrieval_service
from backend.tests.services.reporter.test_memory_evidence_handoff import storyline_match
from backend.tests.services.reporter.test_memory_tools import (
    SEASON_ID, TACO_FRANCHISE_ID, WIRE_FRANCHISE_ID, FrozenData, _call, _registered,
)


def _callback_match(*, parent: UUID | None = None) -> HydratedMemoryMatch:
    source = storyline_match()
    callback = Trigger(
        item=source.memory.item.model_copy(update={
            "kind": MemoryKind.TRIGGER, "item_id": uuid4(), "agent_key": "due_review",
        }),
        version=source.memory.version.model_copy(update={"version_id": uuid4()}),
        content=TriggerContent.model_validate({
            "trigger_type": "scheduled_review", "status": "open", "fire_policy": "one_shot",
            "target_competition_season_id": SEASON_ID,
            "target_storyline_item_id": parent or uuid4(), "target_week": 8,
            "condition": {"kind": "scheduled_review", "review_question": "Did the trade help?"},
        }),
    )
    return source.model_copy(update={"memory": callback})


def _callback_setup(match: HydratedMemoryMatch | None = None, *, writable: bool = True):
    match = match or _callback_match()
    registry, context, memory, _, adapter = _registered(
        matches=(match,), allow_memory_writes=writable,
    )
    context.memory_closeout = MemoryCloseoutState(
        procedure="# Closeout", memory_writes_enabled=writable,
        proposal_snapshot=memory.proposal_snapshot,
    )
    context.memory_closeout.activate(turn=1)
    handle = adapter._presentation.handle_for(match.memory)
    return registry, context, memory, adapter, handle, match


@pytest.mark.parametrize("action", ["resolve", "reschedule", "defer"])
def test_callback_action_keeps_identity_and_records_only_successful_outcome(action: str) -> None:
    registry, context, memory, _, handle, match = _callback_setup()
    arguments = {"update_handle": handle, "action": action, "reason": "Reviewed contribution."}
    if action == "reschedule":
        arguments["target_week"] = 10

    result = _call(registry, "update_memory_callback", **arguments)
    repeated = _call(registry, "update_memory_callback", **arguments)

    assert result["ok"] is True and repeated["ok"] is True
    proposals = memory.proposal_snapshot()
    assert len(proposals) == (0 if action == "defer" else 1)
    if proposals:
        proposal = proposals[0]
        assert proposal.item_id == match.memory.item.item_id
        assert proposal.content.condition == match.memory.content.condition
        assert proposal.content.target_storyline_item_id == match.memory.content.target_storyline_item_id
        assert proposal.content.status.value == ("satisfied" if action == "resolve" else "open")
        assert proposal.content.target_week == (10 if action == "reschedule" else 8)
    else:
        assert result["outcome"] == "uninvestigated"
        assert match.memory.content.status.value == "open" and match.memory.content.target_week == 8
    completed = complete_memory_review(context)
    assert len(completed["callback_dispositions"]) == 1
    assert completed["callback_dispositions"][0]["action"] == action


@pytest.mark.parametrize("target_week", [None, 7, 8])
def test_invalid_reschedule_has_no_proposal_or_closeout_disposition(target_week: int | None) -> None:
    registry, context, memory, adapter, handle, _ = _callback_setup()
    result = _call(registry, "update_memory_callback", update_handle=handle,
        action="reschedule", reason="Later evidence needed.", target_week=target_week)
    assert result["error"]["code"] == "future_review_week_required"
    assert not memory.proposal_snapshot()
    assert adapter._callback_dispositions == {}
    assert context.memory_closeout.callback_dispositions == []


@pytest.mark.parametrize("boundary", ["version_season", "target_season", "read_only", "writes_disabled"])
def test_historical_and_read_only_callbacks_cannot_change_or_defer(boundary: str) -> None:
    match = _callback_match()
    if boundary == "version_season":
        match = match.model_copy(update={"memory": match.memory.model_copy(update={
            "version": match.memory.version.model_copy(update={"competition_season_id": uuid4()}),
        })})
    elif boundary == "target_season":
        match = match.model_copy(update={"memory": match.memory.model_copy(update={
            "content": match.memory.content.model_copy(update={"target_competition_season_id": uuid4()}),
        })})
    registry, context, memory, adapter, handle, _ = _callback_setup(
        match, writable=boundary != "writes_disabled",
    )
    if boundary == "read_only":
        handle = adapter._presentation.handle_for(match.memory, read_only=True)
    for action in ("resolve", "reschedule", "defer"):
        result = _call(registry, "update_memory_callback", update_handle=handle,
            action=action, reason="Historical review.", **({"target_week": 10} if action == "reschedule" else {}))
        if boundary == "writes_disabled":
            assert result["saved"] is False and result["recorded"] is False
        else:
            assert result["ok"] is False
    assert not memory.proposal_snapshot()
    assert context.memory_closeout.callback_dispositions == []


@pytest.mark.parametrize("action", ["resolve", "reschedule"])
def test_defer_cannot_overwrite_successfully_selected_update(action: str) -> None:
    registry, context, memory, _, handle, _ = _callback_setup()
    resolved = _call(registry, "update_memory_callback", update_handle=handle,
        action=action, reason="The next disposition is supported.",
        **({"target_week": 10} if action == "reschedule" else {}))
    assert resolved["saved"] is True

    deferred = _call(registry, "update_memory_callback", update_handle=handle,
        action="defer", reason="Not investigated.")

    assert deferred["ok"] is False
    assert deferred["error"]["code"] == "callback_already_updated"
    assert memory.proposal_snapshot()[0].content.status.value == ("satisfied" if action == "resolve" else "open")
    assert context.memory_closeout.callback_dispositions[0]["action"] == action


@pytest.mark.parametrize("mode,keys,expected", [
    ("merge", ["Waiver Wire"], [TACO_FRANCHISE_ID, WIRE_FRANCHISE_ID]),
    ("merge", [], [TACO_FRANCHISE_ID]),
    ("replace", ["Waiver Wire"], [WIRE_FRANCHISE_ID]),
    ("replace", [], []),
])
def test_storyline_team_edits_preserve_subjects_unless_replacement_is_explicit(
    mode: str, keys: list[str], expected: list[UUID],
) -> None:
    match = storyline_match()
    registry, _, memory, _, adapter = _registered(matches=(match,))
    result = _call(registry, "upsert_storyline_memory_card",
        update_handle=adapter._presentation.handle_for(match.memory),
        headline="Later contender report", summary="The race continues.",
        subjects_mode=mode, team_keys=keys)
    assert result["saved"] is True
    proposal = memory.proposal_snapshot()[0]
    assert [subject.id for subject in proposal.content.subjects] == expected
    assert proposal.content.evidence == match.memory.content.evidence
    assert proposal.content.related_storylines == match.memory.content.related_storylines
    assert proposal.metadata.week == match.memory.version.week
    assert proposal.content.resolution_summary == match.memory.content.resolution_summary


def test_subject_merge_keeps_existing_roles_and_nonteam_subjects() -> None:
    match = storyline_match()
    content = StorylineContent.model_validate({**match.memory.content.model_dump(), "subjects": [
        {"kind": "franchise", "id": TACO_FRANCHISE_ID, "role": "counterparty"},
        {"kind": "player", "id": "7543", "role": "focus"},
    ]})
    match = match.model_copy(update={"memory": match.memory.model_copy(update={"content": content})})
    registry, _, memory, _, adapter = _registered(matches=(match,))
    result = _call(registry, "upsert_storyline_memory_card",
        update_handle=adapter._presentation.handle_for(match.memory),
        headline="Updated trade follow-up", summary="Preserve both perspectives.", team_keys=["Team Taco"])
    assert result["saved"] is True
    assert memory.proposal_snapshot()[0].content.subjects == content.subjects


@pytest.mark.parametrize("seen", [False, True])
def test_storyline_resolution_does_not_cascade_to_seen_or_unseen_callbacks(seen: bool) -> None:
    arc = storyline_match()
    callback = _callback_match(parent=arc.memory.item.item_id)
    registry, context, memory, _, adapter = _registered(matches=(arc, callback))
    context.memory_closeout = MemoryCloseoutState(procedure="# Closeout",
        memory_writes_enabled=True, proposal_snapshot=memory.proposal_snapshot)
    context.memory_closeout.activate(turn=1)
    if seen:
        adapter._presentation.handle_for(callback.memory)
    result = _call(registry, "upsert_storyline_memory_card",
        update_handle=adapter._presentation.handle_for(arc.memory),
        headline="The championship settles the race", summary="The broader arc is resolved.",
        status="resolved", resolution_summary="Final placement is known.")
    assert result["saved"] is True
    assert [proposal.kind for proposal in memory.proposal_snapshot()] == [MemoryKind.STORYLINE]
    assert complete_memory_review(context)["callback_dispositions"] == []
    assert callback.memory.content.status.value == "open"


def test_legacy_successful_trigger_update_records_disposition_without_extra_receipt() -> None:
    registry, context, memory, _, handle, _ = _callback_setup()
    result = _call(registry, "save_storyline_trigger", update_handle=handle,
        status="resolved", resolution_reason="Source evidence answers the question.")
    assert result["saved"] is True
    assert memory.proposal_snapshot()[0].content.status.value == "satisfied"
    assert complete_memory_review(context)["callback_dispositions"][0] == {
        "memory_handle": handle, "action": "resolve", "outcome": "resolved",
        "reason": "Source evidence answers the question.",
    }


def test_failed_embedded_write_rolls_back_callback_proposal_and_disposition() -> None:
    arc = storyline_match()
    callback = _callback_match(parent=arc.memory.item.item_id)
    registry, context, memory, _, adapter = _registered(matches=(arc, callback))
    context.memory_closeout = MemoryCloseoutState(procedure="# Closeout",
        memory_writes_enabled=True, proposal_snapshot=memory.proposal_snapshot)
    context.memory_closeout.activate(turn=1)
    callback_handle = adapter._presentation.handle_for(callback.memory)
    result = _call(registry, "upsert_storyline_memory_card",
        update_handle=adapter._presentation.handle_for(arc.memory),
        headline="A supported update", summary="Only publish a complete proposal bundle.",
        trigger_specs=[
            {"update_handle": callback_handle, "status": "resolved", "resolution_reason": "Answered."},
            {"id": "broken_callback", "trigger_type": "scheduled_review", "target_week": 10},
        ])
    assert result["ok"] is False
    assert memory.proposal_snapshot() == ()
    assert adapter._callback_dispositions == {}
    assert context.memory_closeout.callback_dispositions == []
    repaired = _call(registry, "update_memory_callback", update_handle=callback_handle,
        action="resolve", reason="Answered with the available evidence.")
    assert repaired["saved"] is True
    assert len(memory.proposal_snapshot()) == 1


def test_reschedule_uses_pinned_trade_origin_without_reauthoring_event(database_engine: Engine) -> None:
    domain = _seed_domain(database_engine)
    initial = _generation_context(domain)
    event = initial.propose_event(_trade(domain))
    trigger = initial.propose_trigger(TriggerContent.model_validate({
        "trigger_type": "trade_evaluation", "status": "open", "fire_policy": "one_shot",
        "origin_event_item_id": event.item_id, "target_week": 8,
        "target_competition_season_id": domain.season_id,
        "condition": {"kind": "trade_evaluation"},
    }))
    revision = _service(database_engine, domain).apply(initial.take_completed_bundle()).revision.revision_id
    retrieval, _ = _retrieval_service(database_engine, domain)
    memory = GenerationMemoryContext(
        competition_id=domain.competition_id, generation_id=_add_generation(database_engine, domain),
        pinned_revision_id=revision, retrieval=retrieval, competition_season_id=domain.season_id,
        week=8, knowledge_cutoff_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    registry, context, _, _, _ = _registered()
    register_memory_tools(registry, memory, FrozenData())
    context.memory_closeout = MemoryCloseoutState(procedure="# Closeout",
        memory_writes_enabled=True, proposal_snapshot=memory.proposal_snapshot)
    context.memory_closeout.activate(turn=1)
    found = _call(registry, "search_memory", kinds=["trigger"])
    assert len(found["memories"]) == 1
    result = _call(registry, "update_memory_callback",
        update_handle=found["memories"][0]["memory_handle"], action="reschedule",
        reason="Wait for two more games to assess the trade.", target_week=10)
    assert result["saved"] is True, result
    proposal = memory.proposal_snapshot()[0]
    assert proposal.item_id == trigger.item_id
    assert proposal.content.origin_event_item_id == event.item_id
    assert proposal.content.target_week == 10 and proposal.content.status.value == "open"
    _service(database_engine, domain).apply(memory.take_completed_bundle())
    with database_engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(MemoryVersion)
            .where(MemoryVersion.item_id == trigger.item_id)) == 2
        assert connection.scalar(sa.select(sa.func.count()).select_from(MemoryVersion)
            .where(MemoryVersion.item_id == event.item_id)) == 1
