from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.services.reporter.runner.research_brief import (
    RESEARCH_BRIEF_PATH,
    BriefContext,
    BriefOutlineSection,
    ResearchBrief,
    ResearchBriefError,
    ResearchBriefStore,
    render_research_brief,
)
from backend.services.reporter.runner.state import ArtifactStore, ArtifactStoreError


def _commit(store: ResearchBriefStore, mutation: object) -> None:
    store.commit(mutation, lambda _: None)  # type: ignore[arg-type]


def _fact(store: ResearchBriefStore, fact_id: str, claim: str = "Taco won.") -> None:
    _commit(
        store,
        store.prepare_fact(
            id=fact_id,
            claim_text=claim,
            data_refs=["league_snapshot:week=8", "league_snapshot:week=8"],
            numbers={"wins": 1},
            category="score",
        ),
    )


def test_fact_upsert_is_idempotent_and_preserves_insertion_order() -> None:
    store = ResearchBriefStore()

    first = store.prepare_fact(
        id="fact_taco_win",
        claim_text="Taco won 142.3-98.7.",
        data_refs=["league_snapshot:week=8", "league_snapshot:week=8"],
        numbers={"winner_score": 142.3, "loser_score": 98.7},
        category="score",
    )
    _commit(store, first)
    duplicate = store.prepare_fact(
        id="fact_taco_win",
        claim_text="Taco won 142.3-98.7.",
        data_refs=["league_snapshot:week=8"],
        numbers={"winner_score": 142.3, "loser_score": 98.7},
        category="score",
    )
    _commit(store, duplicate)
    _fact(store, "fact_other")

    assert first.changed is True
    assert duplicate.changed is False
    assert store.brief.revision == 2
    assert [fact.id for fact in store.brief.facts] == [
        "fact_taco_win",
        "fact_other",
    ]
    assert store.brief.facts[0].data_refs == ("league_snapshot:week=8",)


def test_invalid_brief_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ResearchBriefStore().prepare_fact(
            id="Fact 1",
            claim_text="A claim.",
            data_refs=["source"],
        )


def test_references_validate_and_fact_update_marks_dependents_stale() -> None:
    store = ResearchBriefStore()
    _fact(store, "fact_old", "A trade happened in week 3.")
    _fact(store, "fact_current", "The traded player scored 30 in week 8.")
    _commit(
        store,
        store.prepare_memory_callback(
            id="callback_trade_regret",
            callback_type="trade_regret",
            claim_text="The week 3 trade backfired in week 8.",
            old_event_fact_id="fact_old",
            current_event_fact_id="fact_current",
            why_now="The traded player decided the rematch.",
        ),
    )
    _commit(
        store,
        store.prepare_storyline(
            id="story_trade_regret",
            headline="Trade regret arrives",
            summary="The old deal changed the current matchup.",
            supporting_fact_ids=["fact_old", "fact_current"],
            priority=1,
        ),
    )
    _commit(
        store,
        store.prepare_outline(
            sections=[
                BriefOutlineSection(
                    title="Lead",
                    required_fact_ids=("fact_current",),
                    storyline_ids=("story_trade_regret",),
                )
            ]
        ),
    )

    ready = store.brief.readiness()
    assert ready.stale_callback_ids == ()
    assert ready.stale_storyline_ids == ()
    assert ready.outline_stale is False

    _fact(store, "fact_current", "The traded player scored 31 in week 8.")
    stale = store.brief.readiness()
    assert stale.stale_callback_ids == ("callback_trade_regret",)
    assert stale.stale_storyline_ids == ("story_trade_regret",)
    assert stale.outline_stale is True


def test_unknown_references_leave_state_unchanged() -> None:
    store = ResearchBriefStore()

    with pytest.raises(ResearchBriefError) as exc_info:
        store.prepare_storyline(
            id="story_missing",
            headline="Missing",
            summary="No evidence.",
            supporting_fact_ids=["fact_missing"],
        )

    assert exc_info.value.code == "unknown_fact_ids"
    assert store.brief.revision == 0


def test_projection_is_deterministic_and_contains_readiness() -> None:
    brief = ResearchBrief(
        context=BriefContext(
            league_name="Chaos League",
            league_id="league_123",
            week_start=8,
            week_end=8,
        )
    )
    store = ResearchBriefStore(brief=brief)
    _fact(store, "fact_taco_win")

    first = render_research_brief(store.brief)
    second = render_research_brief(store.brief.model_copy(deep=True))

    assert first == second
    assert "League ID: league_123" in first
    assert "### fact_taco_win" in first
    assert "Submission allowed: no" in first
    assert "legacy_facts_unchecked" in first


def test_brief_commit_is_atomic_when_projection_fails() -> None:
    store = ResearchBriefStore()
    mutation = store.prepare_fact(
        id="fact_001",
        claim_text="A verified claim.",
        data_refs=["league_snapshot:week=8"],
    )

    with pytest.raises(RuntimeError, match="recorder failed"):
        store.commit(
            mutation,
            lambda _: (_ for _ in ()).throw(RuntimeError("recorder failed")),
        )

    assert store.brief.revision == 0
    assert store.brief.facts == ()


def test_managed_artifact_syncs_and_blocks_generic_mutations() -> None:
    artifacts = ArtifactStore(managed_paths=frozenset({RESEARCH_BRIEF_PATH}))

    first, created = artifacts.sync_managed(RESEARCH_BRIEF_PATH, "# Brief\n\nOne")
    second, changed = artifacts.sync_managed(RESEARCH_BRIEF_PATH, "# Brief\n\nTwo")
    same, unchanged = artifacts.sync_managed(RESEARCH_BRIEF_PATH, "# Brief\n\nTwo")

    assert created is True
    assert changed is True
    assert unchanged is False
    assert [first.revision, second.revision, same.revision] == [1, 2, 2]

    with pytest.raises(ArtifactStoreError) as exc_info:
        artifacts.edit(
            RESEARCH_BRIEF_PATH,
            old_text="Two",
            new_text="Three",
            expected_revision=2,
        )
    assert exc_info.value.code == "managed_artifact"

    with pytest.raises(ArtifactStoreError) as exc_info:
        artifacts.submit(RESEARCH_BRIEF_PATH, expected_revision=2)
    assert exc_info.value.code == "managed_artifact"


def test_managed_artifact_recording_failure_rolls_back_history() -> None:
    artifacts = ArtifactStore(managed_paths=frozenset({RESEARCH_BRIEF_PATH}))

    with pytest.raises(RuntimeError, match="recording failed"):
        artifacts.sync_managed(
            RESEARCH_BRIEF_PATH,
            "# Brief",
            on_change=lambda _: (_ for _ in ()).throw(
                RuntimeError("recording failed")
            ),
        )
    assert artifacts.artifacts == {}

    artifacts.sync_managed(RESEARCH_BRIEF_PATH, "# Brief\n\nOne")
    with pytest.raises(RuntimeError, match="recording failed"):
        artifacts.sync_managed(
            RESEARCH_BRIEF_PATH,
            "# Brief\n\nTwo",
            on_change=lambda _: (_ for _ in ()).throw(
                RuntimeError("recording failed")
            ),
        )
    assert artifacts.read(RESEARCH_BRIEF_PATH).revision == 1
    assert artifacts.read(RESEARCH_BRIEF_PATH).content.endswith("One")
