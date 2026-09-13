from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Any
from uuid import UUID

import pytest

from backend.resources.memory.common.versioning import (
    MemoryItemIdentity,
    MemoryVersionMetadata,
)
from backend.resources.memory.context_notes import ContextNote, ContextNoteContent
from backend.resources.memory.search_documents import (
    SearchMatchReason,
    SearchScoreComponents,
)
from backend.resources.memory.storylines import Storyline, StorylineContent
from backend.resources.memory.triggers import Trigger, TriggerContent
from backend.services.datalayer import (
    FrozenRosterIdentity,
    ResolvedRosterIdentity,
    RosterIdentityNotFound,
)
from backend.services.memory import (
    GenerationMemoryContext,
    HydratedMemoryMatch,
    MemoryKind,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
)
from backend.services.reporter.config import ReportConfig, TimeRange
from backend.services.reporter.runner.tools.memory_presentation import (
    MemoryPresentationAdapter,
)
from backend.services.reporter.runner.tools.memory_recall import (
    MemoryRecallPlanner,
)


COMPETITION_ID = UUID(int=1)
SEASON_ID = UUID(int=2)
OTHER_SEASON_ID = UUID(int=3)
FRANCHISE_ID = UUID(int=4)
OTHER_FRANCHISE_ID = UUID(int=5)
SEASON_ROSTER_ID = UUID(int=6)
REVISION_ID = UUID(int=7)
CUTOFF = datetime(2026, 10, 20, 12, tzinfo=UTC)


class FrozenData:
    identity = FrozenRosterIdentity(
        competition_id=COMPETITION_ID,
        competition_season_id=SEASON_ID,
        season_roster_id=SEASON_ROSTER_ID,
        franchise_id=FRANCHISE_ID,
        sleeper_roster_id="1",
        team_name="Team Taco",
        manager_name="Alice",
    )

    def resolve_roster_identity(self, key: str) -> Any:
        if key.casefold() in {"team taco", "alice", "1"}:
            return ResolvedRosterIdentity(roster_key=key, identity=self.identity)
        return RosterIdentityNotFound(roster_key=key)

    def get_roster_identity_by_canonical_id(
        self,
        *,
        franchise_id: UUID | None = None,
        season_roster_id: UUID | None = None,
    ) -> FrozenRosterIdentity | None:
        if franchise_id == FRANCHISE_ID or season_roster_id == SEASON_ROSTER_ID:
            return self.identity
        return None

    def get_player_summary(self, player_key: Any) -> dict[str, Any]:
        return {"found": False, "player_key": player_key}


class Retrieval:
    def __init__(
        self,
        *,
        triggers: tuple[HydratedMemoryMatch, ...] = (),
        notes: tuple[HydratedMemoryMatch, ...] = (),
        relevant: tuple[HydratedMemoryMatch, ...] = (),
        fail_kind: MemoryKind | None = None,
    ) -> None:
        self.triggers = triggers
        self.notes = notes
        self.relevant = relevant
        self.fail_kind = fail_kind
        self.requests: list[MemoryRetrievalRequest] = []

    def search(
        self,
        *,
        competition_id: UUID,
        revision_id: UUID,
        request: MemoryRetrievalRequest,
    ) -> MemoryRetrievalResult:
        self.requests.append(request)
        kinds = request.query.kinds
        if kinds == (MemoryKind.TRIGGER,):
            matches = self.triggers
            kind = MemoryKind.TRIGGER
        elif kinds == (MemoryKind.CONTEXT_NOTE,):
            matches = self.notes
            kind = MemoryKind.CONTEXT_NOTE
        else:
            matches = self.relevant
            kind = MemoryKind.STORYLINE
        if kind is self.fail_kind:
            raise RuntimeError(f"{kind.value} retrieval unavailable")
        return MemoryRetrievalResult(
            competition_id=competition_id,
            revision_id=revision_id,
            matches=matches,
        )


def _item(kind: MemoryKind, number: int) -> MemoryItemIdentity:
    return MemoryItemIdentity(
        item_id=UUID(int=number),
        competition_id=COMPETITION_ID,
        kind=kind,
        agent_key=f"{kind.value}-{number}",
        created_at=CUTOFF,
    )


def _version(number: int) -> MemoryVersionMetadata:
    return MemoryVersionMetadata(
        version_id=UUID(int=number + 100),
        revision_number=2,
        content_schema_version=1,
        introduced_revision_id=UUID(int=number + 200),
        creating_generation_id=UUID(int=number + 300),
        recorded_at=CUTOFF,
    )


def _match(memory: Any, *, score: float = 1) -> HydratedMemoryMatch:
    return HydratedMemoryMatch(
        memory=memory,
        score=score,
        score_components=SearchScoreComponents(lexical_rank=score),
        match_reasons=(SearchMatchReason.BROWSE_MATCH,),
    )


def _trigger(
    number: int,
    *,
    status: str = "open",
    policy: str = "one_shot",
    target_week: int | None = 8,
    target_at: datetime | None = None,
    target_season_id: UUID = SEASON_ID,
) -> HydratedMemoryMatch:
    memory = Trigger(
        item=_item(MemoryKind.TRIGGER, number),
        version=_version(number),
        content=TriggerContent.model_validate(
            {
                "trigger_type": "rematch",
                "status": status,
                "fire_policy": policy,
                "target_competition_season_id": target_season_id,
                "target_week": target_week,
                "target_at": target_at,
                "condition": {
                    "kind": "rematch",
                    "franchise_ids": [FRANCHISE_ID, OTHER_FRANCHISE_ID],
                },
            }
        ),
    )
    return _match(memory)


def _note(
    number: int,
    identity: dict[str, Any],
    *,
    status: str = "active",
) -> HydratedMemoryMatch:
    return _match(
        ContextNote(
            item=_item(MemoryKind.CONTEXT_NOTE, number),
            version=_version(number),
            note_identity=identity,
            content=ContextNoteContent(
                narrative=f"Context note {number}",
                outlook="Watch this angle.",
                status=status,
                tags=["continuity"],
            ),
        )
    )


def _storyline(number: int) -> HydratedMemoryMatch:
    return _match(
        Storyline(
            item=_item(MemoryKind.STORYLINE, number),
            version=_version(number),
            content=StorylineContent(
                headline="Taco keeps climbing",
                summary="The contender case strengthened again.",
                status="active",
                salience=4,
                tags=["playoffs"],
                subjects=[],
                evidence=[],
                related_storylines=[],
            ),
        ),
        score=3,
    )


def _plan(
    retrieval: Retrieval,
    *,
    config: ReportConfig | None = None,
    week: int = 8,
    editorial_cutoff_at: datetime | None = None,
) -> Any:
    context = GenerationMemoryContext(
        competition_id=COMPETITION_ID,
        generation_id=UUID(int=99),
        pinned_revision_id=REVISION_ID,
        retrieval=retrieval,
        competition_season_id=SEASON_ID,
        week=week,
        knowledge_cutoff_at=CUTOFF,
        editorial_cutoff_at=editorial_cutoff_at,
    )
    data = FrozenData()
    return MemoryRecallPlanner(
        context,
        data,  # type: ignore[arg-type]
        MemoryPresentationAdapter(data),  # type: ignore[arg-type]
    ).plan(config or ReportConfig(time_range=TimeRange.single_week(week)))


@pytest.mark.parametrize(
    ("policy", "status", "expected"),
    [
        ("one_shot", "open", True),
        ("one_shot", "fired", False),
        ("recurring", "open", True),
        ("recurring", "fired", True),
        ("until_resolved", "open", True),
        ("until_resolved", "fired", True),
        ("until_resolved", "satisfied", False),
        ("recurring", "expired", False),
        ("recurring", "archived", False),
    ],
)
def test_trigger_fire_policy_and_status_are_deterministic(
    policy: str,
    status: str,
    expected: bool,
) -> None:
    trigger = _trigger(10, policy=policy, status=status)
    result = _plan(Retrieval(triggers=(trigger,)))

    assert bool(result.result["due_callbacks"]) is expected
    assert trigger.memory.content.status.value == status


def test_trigger_targets_are_inclusive_and_all_constraints_must_be_due() -> None:
    due = _trigger(10, target_week=8, target_at=CUTOFF)
    future_week = _trigger(11, target_week=9, target_at=CUTOFF)
    future_time = _trigger(12, target_week=8, target_at=CUTOFF + timedelta(seconds=1))
    wrong_season = _trigger(13, target_week=8, target_season_id=OTHER_SEASON_ID)

    result = _plan(
        Retrieval(triggers=(future_week, due, wrong_season, future_time))
    )

    callbacks = result.result["due_callbacks"]
    assert len(callbacks) == 1
    assert callbacks[0]["due_week"] == 8
    assert result.metadata["groups"]["due_callbacks"]["selected_count"] == 1
    assert result.metadata["groups"]["due_callbacks"]["resolved_query"].get(
        "competition_season_id"
    ) is None


def test_simulated_editorial_time_prevents_premature_date_callbacks() -> None:
    editorial = CUTOFF - timedelta(days=365)
    due = _trigger(10, target_at=editorial)
    future = _trigger(11, target_at=editorial + timedelta(seconds=1))
    result = _plan(Retrieval(triggers=(due, future)), editorial_cutoff_at=editorial)
    assert len(result.result["due_callbacks"]) == 1
    scope = result.metadata["resolved_scope"]
    assert scope["editorial_cutoff_at"] == editorial.isoformat()
    assert scope["knowledge_cutoff_at"] == CUTOFF.isoformat()
    assert len(_plan(Retrieval(triggers=(due, future))).result["due_callbacks"]) == 2


def test_context_scope_and_likely_relevance_are_bounded_and_private() -> None:
    notes = (
        _note(20, {"scope": "competition", "note_key": "league"}),
        _note(
            21,
            {
                "scope": "competition_season",
                "competition_season_id": SEASON_ID,
                "note_key": "season",
            },
        ),
        _note(
            22,
            {
                "scope": "competition_season",
                "competition_season_id": OTHER_SEASON_ID,
                "note_key": "other-season",
            },
        ),
        _note(
            23,
            {
                "scope": "franchise",
                "franchise_id": FRANCHISE_ID,
                "note_key": "taco",
            },
        ),
        _note(
            24,
            {
                "scope": "franchise",
                "franchise_id": OTHER_FRANCHISE_ID,
                "note_key": "other-team",
            },
        ),
        _note(25, {"scope": "competition", "note_key": "archived"}, status="archived"),
    )
    relevant = tuple(_storyline(number) for number in range(30, 36))
    retrieval = Retrieval(notes=notes, relevant=relevant)

    result = _plan(
        retrieval,
        config=ReportConfig(
            time_range=TimeRange.single_week(8),
            focus_teams=["Team Taco"],
            focus_hints=["playoff race"],
            custom_instructions="Weekly recap of the contender race",
        ),
    )

    assert [item["scope_label"] for item in result.result["standing_context"]] == [
        "Team Taco",
        "Season",
        "League",
    ]
    assert len(result.result["likely_relevant_memories"]) == 5
    assert result.metadata["groups"]["likely_relevant_memories"]["truncated"] is True
    assert json.loads(result.result_text) == result.result
    assert "pinned_revision_id" not in result.result_text
    assert all(
        binding["result_path"][0]
        in {"standing_context", "likely_relevant_memories"}
        for binding in result.metadata["bindings"]
    )
    relevant_request = retrieval.requests[-1]
    assert retrieval.requests[1].query.competition_season_id is None
    assert relevant_request.query.limit == 6
    assert relevant_request.query.text == "playoff race"
    assert relevant_request.query.week_to == 8
    assert relevant_request.query.statuses == ("active", "dormant")
    assert relevant_request.expand_exact_references is False
    assert relevant_request.expand_stable_references is False


def test_group_failure_degrades_to_partial_prelude() -> None:
    result = _plan(
        Retrieval(
            notes=(_note(20, {"scope": "competition", "note_key": "league"}),),
            fail_kind=MemoryKind.TRIGGER,
        )
    )

    assert result.status == "partial"
    assert result.result["partial"] is True
    assert result.result["due_callbacks"] == []
    assert len(result.result["standing_context"]) == 1
    assert "trigger retrieval unavailable" not in result.result_text
    assert result.metadata["errors"]["due_callbacks"]["type"] == "RuntimeError"


def test_recall_group_budgets_and_stable_ordering() -> None:
    triggers = tuple(
        _trigger(number, target_week=number - 70)
        for number in range(71, 81)
    )
    notes = tuple(
        _note(
            number,
            {"scope": "competition", "note_key": f"league-{number}"},
        )
        for number in range(90, 100)
    )

    result = _plan(Retrieval(triggers=triggers, notes=notes), week=10)

    assert len(result.result["due_callbacks"]) == 8
    assert len(result.result["standing_context"]) == 8
    due_bindings = [
        binding
        for binding in result.metadata["bindings"]
        if binding["result_path"][0] == "due_callbacks"
    ]
    assert [binding["item_id"] for binding in due_bindings] == [
        str(UUID(int=number)) for number in range(80, 72, -1)
    ]
    assert result.metadata["groups"]["due_callbacks"]["truncated"] is True
    assert result.metadata["groups"]["standing_context"]["truncated"] is True


def test_empty_and_fully_failed_recall_remain_explicit_model_context() -> None:
    empty = _plan(Retrieval())
    assert empty.status == "complete"
    assert empty.result["partial"] is False
    assert empty.result["due_callbacks"] == []
    assert "No automatic reporter memory" in empty.result["notice"]

    class FailedRetrieval(Retrieval):
        def search(self, **kwargs: Any) -> MemoryRetrievalResult:
            del kwargs
            raise RuntimeError("private database endpoint failed")

    failed = _plan(
        FailedRetrieval(),
        config=ReportConfig(
            time_range=TimeRange.single_week(8),
            custom_instructions="weekly recap",
        ),
    )
    assert failed.status == "failed"
    assert failed.result["partial"] is True
    assert failed.result["due_callbacks"] == []
    assert "private database endpoint" not in failed.result_text
    assert set(failed.metadata["errors"]) == {
        "due_callbacks",
        "standing_context",
        "storyline_review_pool",
    }


def test_review_lead_preserves_full_narrative_and_bindings_describe_delivered_projection() -> None:
    match = _storyline(30)
    content = match.memory.content.model_copy(update={
        "headline": "H" * 200, "summary": "S" * 550, "callback_condition": "C" * 350,
    })
    match = match.model_copy(update={"memory": match.memory.model_copy(update={"content": content})})
    result = _plan(Retrieval(relevant=(match,)))
    lead = result.result["storyline_review_pool"][0]
    assert (len(lead["headline"]), len(lead["summary"]), len(lead["callback_condition"])) == (200, 550, 350)
    assert lead["truncated"] is False
    assert result.metadata["groups"]["storyline_review_pool"]["truncated"] is False
    binding, = result.metadata["bindings"]
    assert binding["result_path"] == ["storyline_review_pool", 0]
    assert binding["clipped_fields"] == []
    assert "subjects" not in binding["omitted_fields"]
    assert not any("." in field for field in binding["omitted_fields"])
