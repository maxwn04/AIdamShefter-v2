"""Cross-season public discovery, selected inspection, and retained-shape budgets."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import sqlalchemy as sa

from backend.database.models.core.competitions import CompetitionSeason
from backend.database.models.core.franchises import SeasonRoster
from backend.resources.memory.storylines import StorylineContent
from backend.resources.memory.triggers import TriggerContent
from backend.services.datalayer import FrozenRosterIdentity, ResolvedRosterIdentity, RosterIdentityNotFound
from backend.services.memory import GenerationMemoryContext, MemoryMutationOrigin, MemoryKind
from backend.services.reporter.runner.tools.memory_tools import register_memory_tools
from backend.services.reporter.config import ReportConfig
from backend.tests.database.conftest import database_engine, migrated_database
from backend.tests.services.memory.test_mutation_service import _add_generation, _event, _fact, _service
from backend.tests.services.memory.test_retrieval_service import _committed_bundle, _retrieval_service
from backend.tests.services.reporter.test_memory_tools import _call, _registered
from backend.tests.services.datalayer.test_frozen_query_runtime import v3_ready_snapshot


class SeasonalData:
    def __init__(self, domain, historical_season):
        self.domain = domain
        self.historical_season = historical_season

    def available_seasons(self):
        return (
            SimpleNamespace(competition_season_id=self.historical_season, season_year=2025, role="history", through_week=17),
            SimpleNamespace(competition_season_id=self.domain.season_id, season_year=2026, role="primary", through_week=17),
        )

    def get_roster_identity_by_canonical_id(self, *, franchise_id=None, season_roster_id=None, season=None):
        if season_roster_id is not None:
            franchise_id = {UUID(int=100): self.domain.winner_id,
                            UUID(int=101): self.domain.loser_id}.get(season_roster_id)
        if franchise_id not in (self.domain.winner_id, self.domain.loser_id):
            return None
        year = season or 2026
        return FrozenRosterIdentity(competition_id=self.domain.competition_id,
            competition_season_id=self.historical_season if year == 2025 else self.domain.season_id,
            season_roster_id=UUID(int=100 if franchise_id == self.domain.winner_id else 101),
            franchise_id=franchise_id, sleeper_roster_id="7" if year == 2025 else "1",
            team_name="Old Guard" if year == 2025 else "Current Guard")

    def resolve_roster_identity(self, key, *, season=None):
        year = season or 2026
        if key not in ({"Old Guard", "7"} if year == 2025 else {"Current Guard", "1"}):
            return RosterIdentityNotFound(roster_key=key)
        return ResolvedRosterIdentity(roster_key=key,
            identity=self.get_roster_identity_by_canonical_id(franchise_id=self.domain.winner_id, season=year))

    def get_player_summary(self, key):
        return {"found": False}


def test_public_selectors_and_labels_use_real_frozen_renamed_franchise(v3_ready_snapshot, tmp_path):
    from backend.services.datalayer import FrozenLeagueData
    from backend.tests.services.datalayer.test_frozen_query_history import _changed_franchise_artifact
    from backend.tests.services.datalayer.test_snapshot_sqlite_v3 import SHARED_FRANCHISE_ID
    from backend.tests.services.reporter.test_memory_evidence_handoff import storyline_match

    ready = v3_ready_snapshot.model_copy(update={
        "artifact": _changed_franchise_artifact(v3_ready_snapshot, tmp_path)})
    with FrozenLeagueData.open(ready) as data:
        seasons = data.available_seasons()
        old = next(scope for scope in seasons if scope.role == "history")
        primary = next(scope for scope in seasons if scope.role == "primary")
        match = storyline_match()
        canonical = match.memory.model_copy(update={
            "item": match.memory.item.model_copy(update={"competition_id": primary.competition_id}),
            "version": match.memory.version.model_copy(update={"competition_season_id": old.competition_season_id}),
            "content": _arc(SimpleNamespace(winner_id=SHARED_FRANCHISE_ID), "Historical trade hypothesis."),
        })
        registry, _, memory, retrieval, _ = _registered()
        retrieval.matches = (match.model_copy(update={"memory": canonical}),)
        scoped = GenerationMemoryContext(competition_id=primary.competition_id, generation_id=uuid4(),
            pinned_revision_id=memory.pinned_revision_id, retrieval=retrieval,
            competition_season_id=primary.competition_season_id, week=3)
        register_memory_tools(registry, scoped, data)
        for key in ("Old Guard", "Current Guard", f"franchise:{SHARED_FRANCHISE_ID}"):
            found = _call(registry, "search_memory", team_keys=[key])
            assert found["memories"][0]["subjects"][0] == {
                "label": "Old Guard", "role": "focus", "team_key": f"franchise:{SHARED_FRANCHISE_ID}"}
            assert retrieval.calls[-1].query.allowed_season_weeks == {
                old.competition_season_id: 18, primary.competition_season_id: 3}
            assert f"franchise:{SHARED_FRANCHISE_ID}" in retrieval.calls[-1].query.required_entity_keys
            assert len(retrieval.calls[-1].query.required_entity_keys) == 3


def _origin(engine, domain, revision, *, season=None, week=17):
    return MemoryMutationOrigin(generation_id=_add_generation(engine, domain),
        expected_revision_id=revision, competition_season_id=season or domain.season_id, week=week)


def _arc(domain, summary, *, evidence=()):
    return StorylineContent.model_validate({
        "headline": "Amon-Ra trade payoff and the rebuild", "summary": summary,
        "status": "active", "salience": 4, "tags": ["trade", "rebuild"],
        "subjects": [{"kind": "franchise", "id": domain.winner_id, "role": "focus"}],
        "evidence": list(evidence), "related_storylines": [],
    })


def test_franchise_selector_rediscovers_roster_only_storyline_and_fact(database_engine):
    domain, ids, revision = _committed_bundle(database_engine)
    old_season = uuid4()
    with database_engine.begin() as connection:
        connection.execute(sa.insert(CompetitionSeason), {"id": old_season,
            "competition_id": domain.competition_id, "season_year": 2025,
            "sequence_number": 0, "sleeper_league_id": str(old_season)})
        connection.execute(sa.insert(SeasonRoster), [
            {"id": UUID(int=100 + index), "competition_id": domain.competition_id,
             "competition_season_id": old_season, "franchise_id": franchise,
             "sleeper_roster_id": str(index + 7)}
            for index, franchise in enumerate((domain.winner_id, domain.loser_id))])
    mutations = _service(database_engine, domain)
    for index in range(2):
        arc = _arc(domain, "Roster-only hypothesis.")
        arc = StorylineContent.model_validate({**arc.model_dump(),
            "subjects": [{"kind": "season_roster", "id": UUID(int=100 + index), "role": "focus"}]})
        result = mutations.create_storyline(_origin(database_engine, domain, revision, season=old_season), arc)
        revision = result.revision.revision_id
        fact = _fact(domain, ids["event_version"])
        fact = type(fact).model_validate({**fact.model_dump(), "claim": "Roster-only prior fact.",
            "subjects": [{"kind": "season_roster", "id": UUID(int=100 + index), "role": "subject"}]})
        result = mutations.create_fact(_origin(database_engine, domain, revision, season=old_season), fact)
        revision = result.revision.revision_id
    service, _ = _retrieval_service(database_engine, domain)
    memory = GenerationMemoryContext(competition_id=domain.competition_id, generation_id=uuid4(),
        pinned_revision_id=revision, retrieval=service, competition_season_id=domain.season_id, week=17)
    registry, _, _, _, _ = _registered()
    register_memory_tools(registry, memory, SeasonalData(domain, old_season))
    result = _call(registry, "search_memory", text="roster-only", team_keys=["Current Guard"])
    assert {entry["kind"] for entry in result["memories"]} == {"storyline", "fact"}
    assert len(result["memories"]) == 2
    selector = result["memories"][0]["subjects"][0]["team_key"]
    assert selector == f"franchise:{domain.winner_id}"
    assert _call(registry, "search_memory", text="roster-only", team_keys=[selector]) == result


def test_cross_season_query_reports_matches_misses_and_selective_inspection(database_engine, tmp_path):
    domain, ids, revision = _committed_bundle(database_engine)
    old_season = uuid4()
    with database_engine.begin() as connection:
        connection.execute(sa.insert(CompetitionSeason), {"id": old_season,
            "competition_id": domain.competition_id, "season_year": 2025,
            "sequence_number": 0, "sleeper_league_id": str(old_season)})
    mutations = _service(database_engine, domain)
    saved = mutations.create_storyline(_origin(database_engine, domain, revision, season=old_season),
        _arc(domain, "Amon-Ra trade payoff remains unassessed. The rebuild question needs source evidence."))
    revision = saved.revision.revision_id
    historical_id = saved.changes[0].item_id
    service, _ = _retrieval_service(database_engine, domain)
    memory = GenerationMemoryContext(competition_id=domain.competition_id, generation_id=uuid4(),
        pinned_revision_id=revision, retrieval=service, competition_season_id=domain.season_id,
        week=17, knowledge_cutoff_at=datetime.now(UTC))
    registry, _, _, _, _ = _registered()
    register_memory_tools(registry, memory, SeasonalData(domain, old_season))
    selector = f"franchise:{domain.winner_id}"
    exact = _call(registry, "search_memory", text="Amon-Ra trade", team_keys=[selector])
    card, = exact["memories"]
    assert card["season"] == 2025 and card["historical"] and card["read_only"]
    assert card["subjects"] == [{"label": "Old Guard", "role": "focus", "team_key": selector}]
    renamed = _call(registry, "search_memory", text="Amon-Ra trade", team_keys=["Current Guard"])
    old_name = _call(registry, "search_memory", text="Amon-Ra trade", team_keys=["Old Guard"])
    assert renamed["memories"] == old_name["memories"] == exact["memories"]
    assert _call(registry, "search_memory", text="Amon-Ra", season=2026)["memories"] == []
    assert _call(registry, "search_memory", text="Amon-Ra", statuses=["resolved"])["memories"] == []
    paraphrase = _call(registry, "search_memory", text="Did acquiring the star receiver justify the draft capital?")
    assert paraphrase["memories"] == []
    fallback = _call(registry, "search_memory", team_keys=[selector], kinds=["storyline"])
    assert card["memory_handle"] in {entry["memory_handle"] for entry in fallback["memories"]}
    facts = _call(registry, "search_memory", team_keys=[selector], kinds=["fact"])
    assert facts["memories"] and all(entry["kind"] == "fact" for entry in facts["memories"])
    inspected = _call(registry, "inspect_memory", memory_handle=card["memory_handle"])
    assert inspected["memories"][0]["summary"] == card["summary"]
    failed = _call(registry, "upsert_storyline_memory_card", update_handle=card["memory_handle"],
        headline="Changed", summary="Cannot rewrite a prior-season hypothesis.")
    assert failed["error"]["code"] == "cross_season_update_unsupported"
    assert memory.proposal_snapshot() == ()
    # Retain actual ordered public results and the known lexical gap for offline review.
    evidence = {"case": "retained-inspired Amon-Ra payoff/rebuild and renamed franchise",
        "historical_item": str(historical_id), "exact": exact, "paraphrase": paraphrase,
        "structured_fallback": fallback, "facts": facts,
        "limitation": "Synthetic canonical inputs; no generated article or provider-token comparison."}
    (tmp_path / "retrieval-results.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("RETRIEVAL_RESULTS " + json.dumps(evidence))


def test_late_arc_history_paging_and_read_only_handles_never_gain_writes(database_engine, tmp_path):
    domain, ids, revision = _committed_bundle(database_engine)
    mutations = _service(database_engine, domain)
    evidence = []
    for _ in range(28):
        event = mutations.create_event(_origin(database_engine, domain, revision), _event(domain))
        revision = event.revision.revision_id
        evidence.append({"kind": "event", "version_id": event.changes[0].version_id, "role": "support"})
    summary = "The championship arc still needs source verification. " * 70
    arc = mutations.create_storyline(_origin(database_engine, domain, revision), _arc(domain, summary, evidence=evidence))
    item_id = arc.changes[0].item_id
    revision = arc.revision.revision_id
    for number in range(1, 17):
        arc = mutations.replace_storyline(_origin(database_engine, domain, revision), item_id, number,
            _arc(domain, f"Version {number + 1}. " + summary, evidence=evidence))
        revision = arc.revision.revision_id
    for number in range(10):
        trigger = mutations.create_trigger(_origin(database_engine, domain, revision),
            TriggerContent.model_validate({"trigger_type": "scheduled_review", "status": "open",
                "fire_policy": "one_shot", "target_competition_season_id": domain.season_id,
                "target_storyline_item_id": item_id, "target_week": 17,
                "condition": {"kind": "scheduled_review", "review_question": f"Unassessed question {number}"}}))
        revision = trigger.revision.revision_id
    service, _ = _retrieval_service(database_engine, domain)
    memory = GenerationMemoryContext(competition_id=domain.competition_id, generation_id=uuid4(),
        pinned_revision_id=revision, retrieval=service, competition_season_id=domain.season_id,
        week=17, knowledge_cutoff_at=datetime.now(UTC))
    registry, _, _, _, _ = _registered()
    adapter = register_memory_tools(registry, memory, SeasonalData(domain, uuid4()))
    cards = _call(registry, "search_memory", text="Amon-Ra", kinds=["storyline"])
    current = cards["memories"][0]
    assert current["summary"] == ("Version 17. " + summary).strip()
    assert not current["clipped"]
    assert current["evidence"] == [] and current["version"] == 17
    first = _call(registry, "inspect_memory", memory_handle=current["memory_handle"], view="history", limit=5)
    assert [entry["version"] for entry in first["memories"]] == [17, 16, 15, 14, 13]
    assert first["has_more"] and first["next_offset"] == 5
    old = first["memories"][-1]
    recalled = _call(registry, "search_memory", text="Amon-Ra")["memories"][0]
    old_again = _call(registry, "inspect_memory", memory_handle=old["memory_handle"])["memories"][0]
    assert old_again["read_only"] and old_again["memory_handle"] == old["memory_handle"]
    assert recalled["memory_handle"] == current["memory_handle"]
    failed = _call(registry, "upsert_storyline_memory_card", update_handle=old_again["memory_handle"],
        headline="Bad old update", summary="Must not advance to the current version.")
    assert failed["error"]["code"] == "read_only_memory_handle"
    assert memory.proposal_snapshot() == ()
    links = _call(registry, "inspect_memory", memory_handle=current["memory_handle"], view="evidence", limit=5)
    assert len(links["memories"]) == 5 and links["has_more"]
    assert all(entry["read_only"] for entry in links["memories"])
    detail = _call(registry, "inspect_memory", memory_handle=current["memory_handle"])
    assert len(detail["memories"][0]["summary"]) > 3000
    recall = adapter.build_recall(ReportConfig.for_week(17))
    assert len(recall.result["due_callbacks"]) == 8
    assert recall.metadata["groups"]["due_callbacks"]["selected_count"] == 11
    linked = recall.result["due_callbacks"][0]["linked_memories"][0]
    assert not linked["read_only"]
    assert linked["memory_handle"] == current["memory_handle"]
    sizes = {key: len(json.dumps(value).encode()) for key, value in {
        "compact_search": cards, "selected_detail": detail, "history_page": first,
        "evidence_page": links, "automatic_8_of_11_callbacks": recall.result}.items()}
    (tmp_path / "late-arc-bytes.json").write_text(json.dumps(sizes, indent=2), encoding="utf-8")
    print("LATE_ARC_BYTES " + json.dumps(sizes))
