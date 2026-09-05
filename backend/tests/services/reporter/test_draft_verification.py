from __future__ import annotations

import json
from dataclasses import replace

import pytest

from backend.services.reporter.runner.draft_verification import verify_draft
from backend.services.reporter.runner.research_brief import ResearchBrief
from backend.services.reporter.runner.state import ArtifactStore
from backend.services.reporter.runner.tools.artifact_tools import create_artifact, edit_artifact, submit_artifact, verify_artifact
from backend.tests.services.reporter.test_artifact_tools import make_ctx
from backend.tests.services.reporter.test_grounding import catalog, fact, record


def test_actual_draft_returns_source_movements_and_draft_capital_framing() -> None:
    sent = record(tool="team_transactions", subject="Lebron", perspective="sent", fields={"player_name": "Kenneth Walker"})
    received = replace(sent, ref="e1_0.r2", perspective="received", fields={"player_name": "DJ Moore", "net_draft_picks": 1})
    claim = fact(sent, received, category="transaction", field="player_name")
    brief = ResearchBrief(revision=1, facts=(claim,))
    artifact = ArtifactStore().create("article.md", "Lebron received Kenneth Walker and sent DJ Moore. Lebron spent future flexibility.")
    receipt = verify_draft(artifact, brief, catalog(sent, received))
    codes = [item.code for item in receipt.diagnostics]
    assert "trade_direction" not in codes
    assert "transaction_wording" not in codes
    card, = receipt.directional_review_cards
    assert card.source_team == "Lebron"
    assert [asset.identity for asset in card.sent] == [{"player_name": "Kenneth Walker"}]
    assert [asset.identity for asset in card.received] == [{"player_name": "DJ Moore"}]
    assert "draft_capital_framing" in codes
    assert receipt.as_dict()["status"] == "DIAGNOSTIC"
    assert not receipt.traceability_errors


_REVERSED_PARAGRAPH = (
    "FANTASY IS LUCK, meanwhile, is 2-2 after the loss and has been active in reshaping its roster. "
    "In addition to the Chuba deal, it sent Juwan Johnson to caydengu and received Rhamondre Stevenson and Chris Olave. "
    "Those moves are less about Week 2's box score than about trying to correct the shape of the roster before the standings harden."
)


def _trade_source():
    sent = record(tool="team_transactions", subject="caydengu", perspective="sent", fields={
        "player_name": "Juwan Johnson", "status": "complete", "occurred_at": "2025-09-16T14:00:00Z",
    })
    received = replace(sent, ref="e1_0.r2", perspective="received", fields={
        **sent.fields, "player_name": "Rhamondre Stevenson",
    })
    olave = replace(received, ref="e1_0.r3", fields={**received.fields, "player_name": "Chris Olave"})
    return sent, received, olave


def test_observed_pronoun_reversal_gets_source_card_and_entire_paragraph() -> None:
    records = _trade_source()
    claim = fact(*records, category="transaction", field="player_name")
    claim.id = "fact_trade_caydengu"
    # Even a reversed saved claim cannot contaminate the source-derived card.
    claim.claim_text = "FANTASY IS LUCK sent Juwan Johnson and received Rhamondre Stevenson and Chris Olave."
    artifact = ArtifactStore().create("article.md", "# Recap\n\n" + _REVERSED_PARAGRAPH + "\n\nThe season continues.")
    receipt = verify_draft(artifact, ResearchBrief(revision=1, facts=(claim,)), catalog(*records))
    card, = receipt.directional_review_cards
    assert card.fact_id == "fact_trade_caydengu" and card.source_team == "caydengu"
    assert [asset.identity["player_name"] for asset in card.sent] == ["Juwan Johnson"]
    assert [asset.identity["player_name"] for asset in card.received] == ["Rhamondre Stevenson", "Chris Olave"]
    assert card.sent[0].ref == records[0].ref
    assert card.sent[0].status == "complete"
    assert card.sent[0].occurred_at == "2025-09-16T14:00:00Z"
    passage, = receipt.directional_review_passages
    assert card.passage_ids == (passage.id,)
    assert passage.text == _REVERSED_PARAGRAPH and not passage.truncated
    assert not any(item.code in {"trade_direction", "transaction_wording"} for item in receipt.diagnostics)
    assert "neither absence nor entailment" in receipt.as_dict()["directional_review_instruction"]
    assert not receipt.as_dict()["submission_blocking"]


@pytest.mark.parametrize("draft", [
    "Juwan Johnson was received by FANTASY IS LUCK from caydengu. Rhamondre Stevenson and Chris Olave went the other way.",
    "FIL received J. Johnson from cay; RS and CO went the other way.",
    "FANTASY IS LUCK received Juwan Johnson. It sent Rhamondre Stevenson and Chris Olave in return.",
])
def test_passive_abbreviated_or_pronoun_wording_gets_no_direction_verdict(draft: str) -> None:
    records = _trade_source()
    receipt = verify_draft(
        ArtifactStore().create("article.md", draft),
        ResearchBrief(revision=1, facts=(fact(*records, category="transaction", field="player_name"),)),
        catalog(*records),
    )
    assert len(receipt.directional_review_cards) == 1
    assert not any(item.code == "trade_direction" for item in receipt.diagnostics)
    assert all(passage.text == draft for passage in receipt.directional_review_passages)
    if "J. Johnson" in draft:
        assert receipt.directional_review_cards[0].passage_ids == ()


@pytest.mark.parametrize("broken", ["missing", "unavailable", "wrong_binding"])
def test_untraceable_assets_never_become_source_cards(broken: str) -> None:
    item = _trade_source()[0]
    claim = fact(item, category="transaction", field="player_name")
    if broken == "wrong_binding":
        claim.bindings = (claim.bindings[0].model_copy(update={"value": "Imagined Player"}),)
    source = catalog() if broken == "missing" else catalog(replace(item, outcome="unavailable") if broken == "unavailable" else item)
    receipt = verify_draft(ArtifactStore().create("article.md", _REVERSED_PARAGRAPH), ResearchBrief(revision=1, facts=(claim,)), source)
    assert receipt.traceability_errors
    assert not receipt.directional_review_cards and not receipt.directional_review_passages
    assert not receipt.as_dict()["submission_blocking"]


def test_shared_passages_and_selected_assets_are_deduplicated_without_losing_caveats() -> None:
    records = _trade_source()
    first = fact(records[0], category="transaction", field="player_name")
    first.bindings += first.bindings
    second = fact(records[1], category="transaction", field="player_name")
    second.id = "fact_second"
    source = replace(records[0], limitations=("Partial transaction coverage.",))
    receipt = verify_draft(ArtifactStore().create("article.md", _REVERSED_PARAGRAPH), ResearchBrief(revision=1, facts=(first, second)), catalog(source, records[1]))
    assert len(receipt.directional_review_cards) == 2
    assert len(receipt.directional_review_passages) == 1
    assert receipt.directional_review_cards[0].passage_ids == receipt.directional_review_cards[1].passage_ids
    assert len(receipt.directional_review_cards[0].sent) == 1
    assert receipt.directional_review_cards[0].sent[0].limitations == source.limitations


def test_pick_card_preserves_source_identity_without_inventing_a_player_match() -> None:
    item = record(perspective="sent", fields={"pick_season": "2027", "pick_round": 2, "pick_original_team_name": "Taco"})
    receipt = verify_draft(ArtifactStore().create("article.md", "Taco sent a future second."), ResearchBrief(revision=1, facts=(fact(item, category="transaction", field="pick_round"),)), catalog(item))
    card, = receipt.directional_review_cards
    assert card.sent[0].identity == item.fields
    assert card.sent[0].status is None and card.sent[0].occurred_at is None
    assert not card.passage_ids


def test_directional_review_caps_cards_assets_passages_and_exact_excerpt_length() -> None:
    records = [record(ref=f"e1_0.r{i}", subject=f"Team {i // 13}", perspective="sent", fields={"player_name": f"Player {i:03}"}) for i in range(26)]
    claims = [fact(*records[:13], category="transaction", field="player_name")]
    claims.extend(fact(item, category="transaction", field="player_name") for item in records[13:])
    for index, claim in enumerate(claims):
        claim.id = f"fact_{index}"
    paragraphs = [f"Player {i:03} was received by somebody. " + "Context. " * 300 for i in range(26)]
    receipt = verify_draft(ArtifactStore().create("article.md", "\n\n".join(paragraphs)), ResearchBrief(revision=1, facts=tuple(claims)), catalog(*records))
    assert receipt.truncated and len(receipt.directional_review_cards) == 12
    assert len(receipt.directional_review_cards[0].sent) == 12
    assert receipt.directional_review_cards[0].truncated
    assert len(receipt.directional_review_cards[0].passage_ids) <= 2
    assert len(receipt.directional_review_passages) <= 8
    assert sum(len(p.text) for p in receipt.directional_review_passages) <= 12_000
    assert all(len(p.text) <= 2400 and p.truncated for p in receipt.directional_review_passages)
    assert receipt.directional_review_passages[0].text == paragraphs[0][:2400]


@pytest.mark.parametrize(("paragraph_size", "expected_passages"), [(100, 8), (2000, 6)])
def test_shared_pool_count_and_total_character_caps_are_reported(paragraph_size: int, expected_passages: int) -> None:
    records = [record(ref=f"e1_0.r{i}", perspective="sent", fields={"player_name": f"Player {i:03}"}) for i in range(10)]
    claims = [fact(item, category="transaction", field="player_name") for item in records]
    for index, claim in enumerate(claims):
        claim.id = f"fact_{index}"
    paragraphs = [(f"Player {i:03} was sent. ").ljust(paragraph_size, "x") for i in range(10)]
    receipt = verify_draft(ArtifactStore().create("article.md", "\n\n".join(paragraphs)), ResearchBrief(revision=1, facts=tuple(claims)), catalog(*records))
    assert receipt.truncated
    assert len(receipt.directional_review_passages) == expected_passages
    assert receipt.directional_review_cards[-1].truncated
    assert not receipt.directional_review_cards[-1].passage_ids
    assert [p.text for p in receipt.directional_review_passages] == paragraphs[:expected_passages]


def test_window_cutoff_marks_otherwise_short_final_passage_incomplete() -> None:
    item = _trade_source()[0]
    content = "x" * 29_800 + "\n\nJuwan Johnson was sent. " + "More context. " * 100
    receipt = verify_draft(ArtifactStore().create("article.md", content), ResearchBrief(revision=1, facts=(fact(item, category="transaction", field="player_name"),)), catalog(item))
    card, = receipt.directional_review_cards
    passage, = receipt.directional_review_passages
    assert receipt.truncated and card.truncated and passage.truncated
    assert passage.text == content[29_802:30_000]


def test_generic_category_does_not_claim_specialized_draft_semantics_verified() -> None:
    item = record()
    brief = ResearchBrief(revision=1, facts=(fact(item, category="general"),))
    artifact = ArtifactStore().create("article.md", "Taco is the champion and has the longest streak after last season.")
    receipt = verify_draft(artifact, brief, catalog(item))
    assert {item.code for item in receipt.diagnostics} >= {"championship_wording", "superlative_wording", "comparison_wording"}
    assert all(item.severity == "DIAGNOSTIC" for item in receipt.diagnostics)
    assert all("No subject-matched" in item.message for item in receipt.diagnostics)


@pytest.mark.parametrize("verify_before_submission", [False, True])
def test_verification_warnings_and_traceability_errors_do_not_block_submission(verify_before_submission: bool) -> None:
    ctx = make_ctx()
    create_artifact(ctx, path="article.md", content="The champion has the longest streak [e99_0.r1].")
    checked = None
    if verify_before_submission:
        checked = json.loads(verify_artifact(ctx, path="article.md", expected_revision=1))
    result = json.loads(submit_artifact(ctx, path="article.md", expected_revision=1))
    assert result["ok"]
    if checked is not None:
        assert result["draft_verification"] == checked["verification"]
    assert result["draft_verification"]["diagnostics"]
    assert result["draft_verification"]["traceability_errors"]
    assert result["draft_verification"]["submission_blocking"] is False
    assert result["draft_verification"]["status"] == "TRACEABILITY_ERROR"
    assert ctx.artifacts.submitted_path == "article.md"


def test_article_and_brief_edits_expire_receipt_and_submission_rechecks() -> None:
    ctx = make_ctx()
    create_artifact(ctx, path="article.md", content="An ordinary supported article.")
    assert json.loads(verify_artifact(ctx, path="article.md", expected_revision=1))["ok"]
    first = ctx.draft_verifications["article.md"]
    edit_artifact(ctx, path="article.md", old_text="ordinary", new_text="clear", expected_revision=1)
    assert not first.is_current(ctx.artifacts.read("article.md"), ctx.brief.brief)
    verify_artifact(ctx, path="article.md", expected_revision=2)
    second = ctx.draft_verifications["article.md"]
    mutation = ctx.brief.prepare_storyline(id="story", headline="The lead", summary="Supported story", supporting_fact_ids=["fact_submission_fixture"])
    ctx.commit_brief_mutation(mutation)
    assert not second.is_current(ctx.artifacts.read("article.md"), ctx.brief.brief)
    result = json.loads(submit_artifact(ctx, path="article.md", expected_revision=2))
    assert result["ok"]
    assert result["draft_verification"]["article_revision"] == 2
    assert result["draft_verification"]["brief_revision"] == ctx.brief.brief.revision
    assert result["draft_verification"]["status"] == "DIAGNOSTIC"
    assert result["draft_verification"]["submission_blocking"] is False


def test_draft_checks_are_bounded_and_mark_truncation() -> None:
    item = record()
    brief = ResearchBrief(revision=1, facts=(fact(item),))
    artifact = ArtifactStore().create("article.md", "Taco is the best. " * 3000)
    receipt = verify_draft(artifact, brief, catalog(item))
    assert receipt.truncated
    assert receipt.checked_characters <= 30_000
    assert len(receipt.diagnostics) <= 40
