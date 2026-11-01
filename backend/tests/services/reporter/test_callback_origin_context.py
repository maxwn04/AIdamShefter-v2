"""Synthetic coverage for original questions reached through due callbacks."""
from backend.services.memory import MemoryMutationMetadata
from backend.resources.memory.triggers import TriggerContent
from backend.tests.database.conftest import database_engine, migrated_database
from backend.services.reporter.config import ReportConfig
from backend.tests.services.reporter.test_storyline_origin_context import (
    origin_campaign, seed_two_versions, content,
)
from backend.tests.services.reporter.test_memory_tools import _call


def propose_due(memory, domain, item, week):
    memory.propose_trigger(TriggerContent.model_validate({
        'trigger_type': 'scheduled_review', 'status': 'open', 'fire_policy': 'one_shot',
        'target_competition_season_id': domain.season_id,
        'target_storyline_item_id': item, 'target_week': week,
        'condition': {'kind': 'scheduled_review', 'review_question': 'Can the roster hold its seed?'},
    }), metadata=MemoryMutationMetadata(competition_season_id=domain.season_id, week=week))


def add_due(campaign, *, first=None):
    domain, begin, commit = campaign
    item, _, second = seed_two_versions(campaign, first=first)
    _, memory, _ = begin(3, second)
    memory.replace_storyline(item, 2, content('Can this roster hold its seed?'))
    propose_due(memory, domain, item, 4)
    return item, commit(memory)


def test_callback_link_keeps_original_question_and_current_update_binding(origin_campaign):
    _, begin, commit = origin_campaign
    item, pin = add_due(origin_campaign)
    registry, memory, adapter = begin(4, pin)
    plan = adapter.build_recall(ReportConfig.for_week(4))
    callback, = plan.result['due_callbacks']
    linked = next(x for x in callback['linked_memories'] if x['kind'] == 'storyline')
    origin = linked['original_context']
    assert origin['summary'] == 'An acquisition may improve the weekly floor.'
    assert origin['callback_condition'] == 'Does the acquisition improve the weekly floor?'
    assert 'not current facts' in origin['provenance']
    assert 'memory_handle' not in origin and 'status' not in origin
    assert linked['summary'] == 'Can this roster hold its seed?'
    assert plan.result['storyline_review_pool'] == []
    historical = next(b for b in plan.metadata['bindings'] if b['result_path'][-1] == 'original_context')
    assert historical['result_path'] == ['due_callbacks', 0, 'linked_memories', 0, 'original_context']
    assert historical['item_id'] == str(item) and historical['expected_item_revision'] == 1
    assert memory.proposal_snapshot() == ()
    saved = _call(registry, 'upsert_storyline_memory_card', update_handle=linked['memory_handle'],
        headline='Floor and seed remain distinct', summary='Review the acquisition floor question from source evidence.')
    assert saved['saved']
    proposal, = memory.proposal_snapshot()
    assert proposal.item_id == item and proposal.expected_item_revision == 3
    commit(memory)
    _, _, old = begin(4, pin)
    assert old.build_recall(ReportConfig.for_week(4)).result == plan.result


def test_callback_origin_is_bounded_and_present_with_explicit_focus(origin_campaign):
    _, begin, _ = origin_campaign
    _, pin = add_due(origin_campaign, first=content('S' * 2500, headline='H' * 250, callback='Q' * 500))
    _, memory, adapter = begin(4, pin)
    plan = adapter.build_recall(ReportConfig.for_week(4, focus_hints=['unrelated focus']))
    assert len(plan.result['due_callbacks']) == 1
    origin = plan.result['due_callbacks'][0]['linked_memories'][0]['original_context']
    assert [len(origin[k]) for k in ('headline', 'summary', 'callback_condition')] == [200, 2000, 400]
    assert origin['clipped'] is True
    assert origin['relevant_week'] == 1
    assert plan.result['storyline_review_pool'] == []
    assert memory.proposal_snapshot() == ()


def test_first_version_callback_needs_no_duplicate_origin(origin_campaign):
    domain, begin, commit = origin_campaign
    _, memory, _ = begin(1, domain.root_revision_id)
    saved = memory.propose_storyline(content('Original question.'), metadata=MemoryMutationMetadata(
        competition_season_id=domain.season_id, week=1))
    propose_due(memory, domain, saved.item_id, 2)
    pin = commit(memory)
    _, _, adapter = begin(2, pin)
    linked = adapter.build_recall(ReportConfig.for_week(2)).result['due_callbacks'][0]['linked_memories'][0]
    assert linked['summary'] == 'Original question.'
    assert 'original_context' not in linked


def test_callback_filtered_origin_does_not_fall_back_to_later_history(origin_campaign):
    domain, begin, commit = origin_campaign
    _, memory, _ = begin(8, domain.root_revision_id)
    saved = memory.propose_storyline(content('Future-introduced original.'), metadata=MemoryMutationMetadata(
        competition_season_id=domain.season_id, week=2))
    first = commit(memory)
    _, memory, _ = begin(3, first)
    memory.replace_storyline(saved.item_id, 1, content('Eligible current assessment.'))
    propose_due(memory, domain, saved.item_id, 4)
    pin = commit(memory)
    _, _, adapter = begin(4, pin)
    linked = adapter.build_recall(ReportConfig.for_week(4)).result['due_callbacks'][0]['linked_memories'][0]
    assert linked['summary'] == 'Eligible current assessment.'
    assert 'original_context' not in linked


def test_unavailable_origin_does_not_hide_current_callback(origin_campaign, monkeypatch):
    _, begin, _ = origin_campaign
    _, pin = add_due(origin_campaign)
    _, memory, adapter = begin(4, pin)
    def unavailable(*args, **kwargs):
        raise RuntimeError('Synthetic unavailable history')
    monkeypatch.setattr(memory, 'inspect', unavailable)
    plan = adapter.build_recall(ReportConfig.for_week(4))
    linked = plan.result['due_callbacks'][0]['linked_memories'][0]
    assert linked['summary'] == 'Can this roster hold its seed?'
    assert 'original_context' not in linked
    assert linked['origin_context_notice'] == 'Original storyline context unavailable; current linked memory remains shown.'
    assert plan.status == 'partial' and 'due_callbacks' in plan.metadata['errors']
    assert memory.proposal_snapshot() == ()
