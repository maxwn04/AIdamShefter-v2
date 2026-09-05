"""Public callback boundaries and canonical same-item review lifecycle."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from backend.database.models.memory import MemoryItem, MemoryVersion
from backend.resources.memory.triggers import TriggerContent
from backend.resources.memory.triggers.validation import InvalidTradeOriginError
from backend.services.memory import GenerationMemoryContext
from backend.services.reporter.config import ReportConfig
from backend.services.reporter.runner.tools.memory_tools import register_memory_tools
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.services.memory.test_mutation_service import (
    _add_generation, _generation_context, _seed_domain, _service,
)
from backend.tests.services.memory.test_retrieval_service import _retrieval_service
from backend.tests.services.reporter.test_memory_evidence_handoff import setup, saved_source_fact
from backend.tests.services.reporter.test_memory_tools import _call, _registered, FrozenData


def save_arc(registry):
    result = _call(registry, "upsert_storyline_memory_card", id="lineup_timing",
        headline="Lineup timing", summary="Review whether the early lineup edge persists.")
    assert result["saved"] is True
    return result


def test_schedule_requires_storyline_week_and_question_and_defaults_one_shot():
    registry, _, memory, _, _, _ = setup()
    save_arc(registry)
    for missing in ("storyline_id", "target_week", "condition"):
        arguments = dict(id="review", trigger_type="scheduled_review", storyline_id="lineup_timing",
            target_week=2, condition={"review_question": "Does the lineup edge persist?"})
        arguments.pop(missing)
        result = _call(registry, "save_storyline_trigger", **arguments)
        assert result["saved"] is False
        assert len(memory.proposal_snapshot()) == 1
    saved = _call(registry, "save_storyline_trigger", id="review", trigger_type="scheduled_review",
        storyline_id="lineup_timing", target_week=2, condition={"review_question": "Does the lineup edge persist?"})
    assert saved["saved"] is True
    content = memory.proposal_snapshot()[-1].content
    assert content.fire_policy.value == "one_shot"
    assert content.target_competition_season_id == memory.competition_season_id
    assert content.origin_event_item_id is None


@pytest.mark.parametrize("kind,condition", [
    ("trade_evaluation", {"event_id": "week1_matchup"}),
    ("trade_evaluation", {"roster_keys": ["Team Taco", "Waiver Wire"]}),
    ("scheduled_review", {"review_question": "Follow up?", "ignored": "bad"}),
    ("rematch", {"roster_keys": ["Team Taco", "Waiver Wire"], "event_id": "week1_matchup"}),
])
def test_misplaced_or_wrong_condition_fields_select_nothing(kind, condition):
    registry, _, memory, _, _, _ = setup()
    result = _call(registry, "save_storyline_trigger", id="invalid", trigger_type=kind,
        target_week=2, condition=condition)
    assert result["saved"] is False
    assert memory.proposal_snapshot() == ()


def test_trade_and_rematch_cannot_be_manufactured_from_wrong_origin():
    registry, context, memory, _, _, _ = setup()
    saved_source_fact(registry, context, week=3)
    with context.bind_tool_execution(UUID(int=77)):
        saved = _call(registry, "save_memory_event", id="week1_matchup", event_type="matchup",
            source_fact_ids=["fact_event"], headline="Win", summary="Supported matchup.")
    assert saved["saved"] is True
    trade = _call(registry, "save_storyline_trigger", id="bad_trade", trigger_type="trade_evaluation",
        event_id="week1_matchup", target_week=4, condition={})
    assert trade["error"]["code"] == "invalid_trigger_origin"
    assert "scheduled_review" in trade["error"]["message"]
    missing = _call(registry, "save_storyline_trigger", id="bad_rematch", trigger_type="rematch",
        target_week=4, condition={"roster_keys": ["Team Taco", "Waiver Wire"]})
    assert missing["error"]["code"] == "missing_trigger_origin"
    assert len(memory.proposal_snapshot()) == 1
    valid = _call(registry, "save_storyline_trigger", id="real_rematch", trigger_type="rematch",
        event_id="week1_matchup", target_week=4, condition={"roster_keys": ["Team Taco", "Waiver Wire"]})
    assert valid["saved"] is True


def test_trade_review_accepts_source_backed_trade_selected_in_same_run():
    registry, context, memory, _, _, data = setup()
    data.add_trade()
    saved_source_fact(registry, context, "transactions", week_from=2, week_to=2)
    with context.bind_tool_execution(UUID(int=78)):
        event = _call(registry, "save_memory_event", id="trade", event_type="trade",
            source_fact_ids=["fact_event"], headline="Trade", summary="Source-backed trade.")
    assert event["saved"] is True
    review = _call(registry, "save_storyline_trigger", id="trade_review", trigger_type="trade_evaluation",
        event_id="trade", target_week=4, condition={})
    assert review["saved"] is True
    assert memory.proposal_snapshot()[-1].content.origin_event_item_id == memory.proposal_snapshot()[0].item_id


@pytest.mark.parametrize("reschedule", [False, True])
def test_public_schedule_due_resolve_and_reschedule_use_same_canonical_item(database_engine: Engine, reschedule: bool):
    domain = _seed_domain(database_engine)
    retrieval, _ = _retrieval_service(database_engine, domain)

    def begin(week, revision):
        memory = GenerationMemoryContext(competition_id=domain.competition_id,
            generation_id=_add_generation(database_engine, domain), pinned_revision_id=revision,
            retrieval=retrieval, competition_season_id=domain.season_id, week=week,
            knowledge_cutoff_at=datetime.now(UTC))
        registry, _, _, _, _ = _registered()
        adapter = register_memory_tools(registry, memory, FrozenData())
        return registry, memory, adapter

    registry, memory, adapter = begin(1, domain.root_revision_id)
    arc = save_arc(registry)
    review = _call(registry, "save_storyline_trigger", id="lineup_review", trigger_type="scheduled_review",
        storyline_id=arc["id"], target_week=2, condition={"review_question": "Does the lineup edge persist?"})
    assert review["saved"] is True
    item_id = UUID(review["proposal"]["item_id"])
    revision = _service(database_engine, domain).apply(memory.take_completed_bundle()).revision.revision_id

    registry, memory, adapter = begin(1, revision)
    assert adapter.build_recall(ReportConfig.for_week(1)).result["due_callbacks"] == []
    registry, memory, adapter = begin(2, revision)
    due = adapter.build_recall(ReportConfig.for_week(2)).result["due_callbacks"]
    assert len(due) == 1 and due[0]["condition_summary"] == "Does the lineup edge persist?"
    assert "article mention is optional" in due[0]["review_notice"]
    arguments = {"update_handle": due[0]["memory_handle"]}
    arguments.update({"status": "open", "target_week": 4} if reschedule else
        {"status": "resolved", "resolution_reason": "Reviewed the evidence; no material development worth an article mention."})
    result = _call(registry, "save_storyline_trigger", **arguments)
    assert result["saved"] is True
    selected = memory.proposal_snapshot()[0]
    assert selected.operation == "replace" and selected.item_id == item_id
    assert selected.content.condition.review_question == "Does the lineup edge persist?"
    assert selected.content.target_storyline_item_id == UUID(arc["proposal"]["item_id"])
    revision = _service(database_engine, domain).apply(memory.take_completed_bundle()).revision.revision_id

    _, _, adapter = begin(3, revision)
    assert adapter.build_recall(ReportConfig.for_week(3)).result["due_callbacks"] == []
    _, _, adapter = begin(4, revision)
    due = adapter.build_recall(ReportConfig.for_week(4)).result["due_callbacks"]
    assert len(due) == (1 if reschedule else 0)
    with database_engine.connect() as connection:
        assert connection.scalar(sa.select(sa.func.count()).select_from(MemoryItem).where(MemoryItem.id == item_id)) == 1
        assert connection.scalar(sa.select(sa.func.count()).select_from(MemoryVersion).where(MemoryVersion.item_id == item_id)) == 2


@pytest.mark.parametrize("origin", ["source_trade", "inferred_trade", "matchup"])
def test_canonical_trade_origin_validation_in_atomic_bundle(database_engine: Engine, origin: str):
    from backend.tests.resources.memory.test_event_manager import _seed_domain as seed_event_domain, _trade, _matchup
    domain = seed_event_domain(database_engine)
    context = _generation_context(domain)
    content = _matchup(domain) if origin == "matchup" else _trade(domain)
    if origin == "inferred_trade":
        content = type(content).model_validate({**content.model_dump(), "confidence": "inferred"})
    event = context.propose_event(content)
    context.propose_trigger(TriggerContent.model_validate({
        "trigger_type": "trade_evaluation", "status": "open", "fire_policy": "one_shot",
        "origin_event_item_id": event.item_id, "target_week": 4,
        "condition": {"kind": "trade_evaluation"},
    }))
    service = _service(database_engine, domain)
    if origin == "source_trade":
        assert service.apply(context.take_completed_bundle()).revision is not None
    else:
        with pytest.raises(InvalidTradeOriginError):
            service.apply(context.take_completed_bundle())
        with database_engine.connect() as connection:
            assert connection.scalar(sa.select(sa.func.count()).select_from(MemoryItem).where(MemoryItem.id == event.item_id)) == 0


def test_origin_error_has_stable_http_400_mapping():
    from backend.api.errors.memory import _http_error
    status, code, message = _http_error(InvalidTradeOriginError("Use a scheduled review."))
    assert status == 400 and code == "invalid_trigger_origin"
    assert message == "Use a scheduled review."
