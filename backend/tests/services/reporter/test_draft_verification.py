from __future__ import annotations

import json
from dataclasses import replace

from backend.services.reporter.runner.draft_verification import verify_draft
from backend.services.reporter.runner.research_brief import ResearchBrief
from backend.services.reporter.runner.state import ArtifactStore
from backend.services.reporter.runner.tools.artifact_tools import create_artifact, edit_artifact, submit_artifact, verify_artifact
from backend.tests.services.reporter.test_artifact_tools import make_ctx
from backend.tests.services.reporter.test_grounding import catalog, fact, record


def test_actual_draft_reports_reversed_trade_and_draft_capital_framing() -> None:
    sent = record(tool="team_transactions", subject="Lebron", perspective="sent", fields={"player_name": "Kenneth Walker"})
    received = replace(sent, ref="e1_0.r2", perspective="received", fields={"player_name": "DJ Moore", "net_draft_picks": 1})
    claim = fact(sent, received, category="transaction", field="player_name")
    brief = ResearchBrief(revision=1, facts=(claim,))
    artifact = ArtifactStore().create("article.md", "Lebron received Kenneth Walker and sent DJ Moore. Lebron spent future flexibility.")
    receipt = verify_draft(artifact, brief, catalog(sent, received))
    codes = [item.code for item in receipt.diagnostics]
    assert codes.count("trade_direction") == 2
    assert "draft_capital_framing" in codes
    assert receipt.as_dict()["status"] == "DIAGNOSTIC"
    assert not receipt.traceability_errors


def test_generic_category_does_not_claim_specialized_draft_semantics_verified() -> None:
    item = record()
    brief = ResearchBrief(revision=1, facts=(fact(item, category="general"),))
    artifact = ArtifactStore().create("article.md", "Taco is the champion and has the longest streak after last season.")
    receipt = verify_draft(artifact, brief, catalog(item))
    assert {item.code for item in receipt.diagnostics} >= {"championship_wording", "superlative_wording", "comparison_wording"}
    assert all(item.severity == "DIAGNOSTIC" for item in receipt.diagnostics)
    assert all("No subject-matched" in item.message for item in receipt.diagnostics)


def test_visible_fabricated_reference_cannot_be_submitted() -> None:
    ctx = make_ctx()
    create_artifact(ctx, path="article.md", content="A claim [e99_0.r1].")
    result = json.loads(submit_artifact(ctx, path="article.md", expected_revision=1))
    assert result["error"]["code"] == "evidence_not_ready"
    assert ctx.artifacts.submitted_path is None


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


def test_draft_checks_are_bounded_and_mark_truncation() -> None:
    item = record()
    brief = ResearchBrief(revision=1, facts=(fact(item),))
    artifact = ArtifactStore().create("article.md", "Taco is the best. " * 3000)
    receipt = verify_draft(artifact, brief, catalog(item))
    assert receipt.truncated
    assert receipt.checked_characters <= 30_000
    assert len(receipt.diagnostics) <= 40
