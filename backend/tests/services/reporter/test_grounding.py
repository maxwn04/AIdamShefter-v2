from __future__ import annotations

from dataclasses import replace

import pytest

from backend.services.reporter.runner.evidence import EvidenceCatalog, EvidenceRecord
from backend.services.reporter.runner.grounding import validate_fact
from backend.services.reporter.runner.research_brief import BriefFact, ResearchBriefError


def record(**changes) -> EvidenceRecord:
    return replace(EvidenceRecord(
        ref="e1_0.r1", source="e1_0", tool="team_history", outcome="found",
        subject="Taco", season=2025, week_from=1, week_to=8,
        fields={"wins": 10}, units={"wins": "games"}, complete=True,
        population="league",
    ), **changes)


def binding(item: EvidenceRecord, field: str = "wins") -> dict:
    return dict(ref=item.ref, field=field, value=item.fields[field], subject=item.subject,
                season=item.season, week_from=item.week_from, week_to=item.week_to,
                perspective=item.perspective)


def fact(*items: EvidenceRecord, category="standing", field="wins", **changes) -> BriefFact:
    return BriefFact(id="fact_test", claim_text="A selected factual claim.", revision_at_set=1,
                     data_refs=tuple(item.ref for item in items), bindings=tuple(binding(item, field) for item in items),
                     category=category, **changes)


def catalog(*items: EvidenceRecord) -> EvidenceCatalog:
    result = EvidenceCatalog()
    for source in dict.fromkeys(item.source for item in items):
        result.register(source, tuple(item for item in items if item.source == source))
    return result


@pytest.mark.parametrize("change", [
    {"subject": "Redraft"}, {"season": 2026}, {"week_to": 9}, {"value": 9},
    {"perspective": "received"}, {"field": "losses"}, {"ref": "invented"},
])
def test_rejects_misattributed_bindings(change) -> None:
    item = record()
    claim = fact(item)
    claim.bindings = (claim.bindings[0].model_copy(update=change),)
    with pytest.raises(ResearchBriefError):
        validate_fact(claim, catalog(item))


@pytest.mark.parametrize("outcome", ["not_found", "unavailable"])
def test_transport_success_does_not_support_fact(outcome) -> None:
    item = record(outcome=outcome)
    with pytest.raises(ResearchBriefError):
        validate_fact(fact(item), catalog(item))


def test_plain_legacy_ref_is_readable_but_not_valid_new_support() -> None:
    claim = BriefFact(id="legacy", claim_text="Old claim", data_refs=("old_tool:week=8",), revision_at_set=1)
    assert claim.support_status == "legacy_unchecked"
    with pytest.raises(ResearchBriefError, match="bindings"):
        validate_fact(claim, EvidenceCatalog())


def test_generic_fact_cannot_omit_bindings() -> None:
    claim = fact(record(), category="general")
    claim.bindings = ()
    with pytest.raises(ResearchBriefError):
        validate_fact(claim, catalog(record()))


def test_rounded_binary_float_can_bind_without_truncation() -> None:
    item = record(fields={"points": 1754.9999999999998})
    claim = fact(item, field="points")
    claim.bindings = (claim.bindings[0].model_copy(update={"value": 1755.0}),)
    assert validate_fact(claim, catalog(item))


def test_comparison_uses_durable_identity_across_rename() -> None:
    before = record(subject="FANTASY IS LUCK", subject_id="franchise1")
    after = record(ref="e2_0.r1", source="e2_0", subject="OnlyFannins", subject_id="franchise1", season=2026)
    assert validate_fact(fact(before, after, category="comparison"), catalog(before, after))
    with pytest.raises(ResearchBriefError):
        validate_fact(fact(after, before, category="comparison"), catalog(before, after))
    other = replace(after, subject_id="franchise2")
    with pytest.raises(ResearchBriefError):
        validate_fact(fact(before, other, category="comparison"), catalog(before, other))


def test_superlative_rejects_short_population_and_non_extreme() -> None:
    low = record(fields={"wins": 2})
    selected = record(ref="e1_0.r2", subject="GIBBS", fields={"wins": 6})
    high = record(ref="e1_0.r3", subject="Lebron", fields={"wins": 14})
    with pytest.raises(ResearchBriefError, match="extreme"):
        validate_fact(fact(selected, category="superlative", superlative_direction="max"), catalog(low, selected, high))
    incomplete = replace(high, complete=False)
    with pytest.raises(ResearchBriefError, match="complete"):
        validate_fact(fact(incomplete, category="superlative", superlative_direction="max"), catalog(incomplete))
    assert validate_fact(fact(high, category="superlative", superlative_direction="max"), catalog(low, selected, high))


@pytest.mark.parametrize("tool,bracket,champion", [("standings", "winners", True), ("playoff_picture", "losers", True), ("playoff_picture", "winners", False)])
def test_champion_requires_actual_winners_bracket_outcome(tool, bracket, champion) -> None:
    item = record(tool=tool, fields={"is_champion": champion, "bracket_type": bracket})
    with pytest.raises(ResearchBriefError):
        validate_fact(fact(item, category="championship", field="is_champion"), catalog(item))


def test_transaction_requires_direction_and_preserves_limitations() -> None:
    item = record(tool="team_transactions", perspective="sent", fields={"player_name": "Kenneth Walker"}, limitations=("Draft-pick count does not measure value.",))
    diagnostics = validate_fact(fact(item, category="transaction", field="player_name"), catalog(item))
    assert any("Draft-pick count" in diagnostic for diagnostic in diagnostics)


def test_superlative_direction_and_unique_are_checked() -> None:
    low = record(fields={"wins": 2})
    high = record(ref="e1_0.r2", subject="Lebron", fields={"wins": 14})
    with pytest.raises(ResearchBriefError, match="direction"):
        validate_fact(fact(low, category="superlative"), catalog(low, high))
    with pytest.raises(ResearchBriefError, match="extreme"):
        validate_fact(fact(low, category="superlative", superlative_direction="max"), catalog(low, high))
    assert validate_fact(fact(low, category="superlative", superlative_direction="min"), catalog(low, high))
    tied = replace(high, ref="e1_0.r3", subject="Other")
    with pytest.raises(ResearchBriefError, match="tied"):
        validate_fact(fact(high, category="superlative", superlative_direction="max", superlative_unique=True), catalog(low, high, tied))


def test_transaction_must_select_asset_or_net_count() -> None:
    item = record(tool="team_transactions", perspective="sent", fields={"team_name": "Taco", "player_name": "Kenneth Walker"})
    with pytest.raises(ResearchBriefError, match="selected"):
        validate_fact(fact(item, category="transaction", field="team_name"), catalog(item))
    net = replace(item, perspective=None, fields={"net_draft_picks": 1})
    assert validate_fact(fact(net, category="transaction", field="net_draft_picks"), catalog(net))


def test_cross_season_comparison_rejects_name_only_and_mismatched_windows() -> None:
    before = record()
    after = record(ref="e2_0.r1", source="e2_0", season=2026)
    with pytest.raises(ResearchBriefError, match="durable"):
        validate_fact(fact(before, after, category="comparison"), catalog(before, after))
    before = replace(before, subject_id="same")
    after = replace(after, subject_id="same", week_to=1)
    with pytest.raises(ResearchBriefError, match="windows"):
        validate_fact(fact(before, after, category="comparison"), catalog(before, after))


def test_champion_with_playoff_outcome_is_supported() -> None:
    item = record(tool="playoff_picture", fields={"bracket_type": "winners", "is_champion": True})
    assert validate_fact(fact(item, category="championship", field="is_champion"), catalog(item))
