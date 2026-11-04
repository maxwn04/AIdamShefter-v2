from dataclasses import replace

from backend.services.reporter.runner.draft_verification import verify_draft
from backend.services.reporter.runner.research_brief import ResearchBrief
from backend.services.reporter.runner.state import ArtifactStore
from backend.tests.services.reporter.test_grounding import catalog, fact, record


def check(draft, records, claims=None):
    if claims is None:
        claims = [fact(r) for r in records]
        for i, c in enumerate(claims):
            c.id = f"record_fact_{i}"
    return verify_draft(ArtifactStore().create("article.md", draft),
                        ResearchBrief(revision=1, facts=tuple(claims)), catalog(*records))


def standing(ref="e1_0.r1", **changes):
    return record(ref=ref, subject="Cedar", week_to=4,
                  fields={"wins": 8, "losses": 0, "ties": 0,
                          "record_unit": "standings_decisions"}, **changes)


def contexts(receipt):
    return [d for d in receipt.diagnostics if d.code == "team_record_context"]


def test_correct_multi_team_sentence_is_not_cross_compared():
    cedar = standing()
    birch = replace(cedar, ref="e1_0.r2", subject="Birch", fields={**cedar.fields, "wins": 6, "losses": 2})
    receipt = check("Cedar (8-0) and Birch (6-2) lead the table.", [cedar, birch])
    assert not any(d.code == "team_record_attribution" for d in receipt.diagnostics)
    assert len(contexts(receipt)) == 2
    assert all("not a mismatch verdict" in d.message for d in contexts(receipt))


def test_current_and_historical_periods_remain_distinct():
    current = standing()
    prior = replace(current, ref="e1_0.r2", week_to=3, fields={**current.fields, "wins": 6})
    receipt = check("Through Week 4 Cedar is 8-0, after reaching 6-0 through Week 3.", [current, prior])
    context, = contexts(receipt)
    assert '"week_to": 4' in context.message and '"week_to": 3' in context.message
    assert '"wins": 8' in context.message and '"wins": 6' in context.message
    assert not any(d.code == "team_record_attribution" for d in receipt.diagnostics)


def test_wrong_record_remains_visible_beside_authoritative_source_without_passing_verdict():
    receipt = check("Through Week 4 Cedar is 7-1.", [standing()])
    context, = contexts(receipt)
    assert "7-1" in context.excerpt and '"wins": 8' in context.message
    assert '"losses": 0' in context.message and "Compare" in context.message
    assert "not proof" in context.message and receipt.as_dict()["submission_blocking"] is False


def test_invalid_binding_cannot_supply_authoritative_record_context():
    item = standing()
    claim = fact(item)
    claim.bindings = (claim.bindings[0].model_copy(update={"value": 7}),)
    receipt = check("Cedar is 7-1.", [item], [claim])
    assert receipt.traceability_errors and not contexts(receipt)


def test_claim_text_cannot_poison_source_values_and_repeated_binding_is_deduplicated():
    item = standing()
    claim = fact(item)
    claim.claim_text = "Cedar is 7-1 in a different season."
    claim.bindings += claim.bindings
    second = claim.model_copy(update={"id": "fact_second"})
    receipt = check("Cedar is 7-1.", [item], [claim, second])
    context, = contexts(receipt)
    assert context.message.count('"ref": "e1_0.r1"') == 1
    assert '"wins": 8' in context.message and '"season": 2025' in context.message


def test_ties_units_and_source_limitations_are_preserved():
    item = replace(standing(), fields={"wins": 7, "losses": 0, "ties": 1, "record_unit": "standings_decisions"}, limitations=("Partial source coverage.",))
    context, = contexts(check("Cedar is 7-0-1.", [item]))
    assert '"ties": 1' in context.message and '"record_unit": "standings_decisions"' in context.message
    assert "Partial source coverage." in context.message
    assert '"units":' in context.message


def test_equal_display_names_do_not_merge_distinct_subject_identities():
    first = replace(standing(), subject_id="franchise-one")
    second = replace(first, ref="e1_0.r2", subject_id="franchise-two")
    receipt = check("Cedar is 8-0.", [first, second])
    assert len(contexts(receipt)) == 2
    assert '"subject_id": "franchise-one"' in contexts(receipt)[0].message
    assert '"subject_id": "franchise-two"' in contexts(receipt)[1].message


def test_unknown_source_period_is_not_invented_from_draft_wording():
    item = replace(standing(), season=None, week_from=None, week_to=None, temporal_kind="unknown")
    context, = contexts(check("Through Week 4 of 2025 Cedar is 8-0.", [item]))
    assert '"season": null' in context.message and '"week_to": null' in context.message
    assert '"temporal_kind": "unknown"' in context.message


def test_no_record_claim_does_not_add_review_noise():
    receipt = check("Cedar has a promising young roster.", [standing()])
    assert not contexts(receipt)


def test_review_context_is_bounded_and_reports_omissions():
    records = [replace(standing(ref=f"e1_0.r{i}"), subject=f"Club {i // 5}", week_to=i % 5 + 1) for i in range(65)]
    draft = "\n\n".join(f"Club {i} (8-0): " + "Context " * 200 for i in range(13))
    receipt = check(draft, records)
    assert len(contexts(receipt)) == 12 and receipt.truncated
    assert sum(len(d.excerpt) for d in contexts(receipt)) <= 6000
    assert all(len(d.excerpt) <= 1200 for d in contexts(receipt))
    assert all(d.message.count('"ref":') <= 4 for d in contexts(receipt))
