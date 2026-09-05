"""Real source adapters, saved facts, frozen SQLite and canonical memory handoff."""
from __future__ import annotations

import inspect
import json
import sqlite3
from uuid import UUID, uuid4

import pytest

from backend.resources.memory.events.payloads.trade import DraftPickTradeAsset
from backend.resources.memory.storylines import Storyline, StorylineContent
from backend.services.datalayer.query.contracts import SnapshotSeason
from backend.services.datalayer.query.curated.transactions import _group_transaction_rows
from backend.services.memory import GenerationMemoryContext, HydratedMemoryMatch, MemoryKind
from backend.services.reporter.runner.tools.brief_tools import save_fact
from backend.services.reporter.runner.tools.datalayer_tools import register_datalayer_tools
from backend.services.reporter.runner.tools.memory_tools import register_memory_tools
from backend.tests.services.reporter.test_memory_tools import (
    COMPETITION_ID, SEASON_ID, TACO_FRANCHISE_ID, WIRE_FRANCHISE_ID,
    FrozenData, RecordingRetrieval, _call, _event_match, _registered,
)


class SQLiteData(FrozenData):
    def __init__(self) -> None:
        super().__init__()
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            CREATE TABLE games(league_id TEXT, week INTEGER, matchup_id INTEGER,
                roster_id_a INTEGER, roster_id_b INTEGER, points_a REAL, points_b REAL, winner_roster_id INTEGER);
            CREATE TABLE roster_identities(league_id TEXT, roster_id INTEGER, franchise_id TEXT);
            CREATE TABLE team_profiles(league_id TEXT, roster_id INTEGER, team_name TEXT);
            CREATE TABLE transactions(league_id TEXT,transaction_id TEXT,week INTEGER,type TEXT,status TEXT,created_ts INTEGER);
            CREATE TABLE transaction_moves(league_id TEXT,transaction_id TEXT,move_index INTEGER,roster_id INTEGER,
                player_id TEXT,asset_type TEXT,direction TEXT,bid_amount INTEGER,from_roster_id INTEGER,to_roster_id INTEGER,
                pick_season TEXT,pick_round INTEGER,pick_original_roster_id INTEGER,pick_id TEXT);
            CREATE TABLE players(player_id TEXT,full_name TEXT);
            INSERT INTO games VALUES ('league',3,6,1,2,143.84,116.10,1);
            INSERT INTO team_profiles VALUES ('league',1,'Team Taco'),('league',2,'Waiver Wire');
        """)
        self.connection.executemany("INSERT INTO roster_identities VALUES ('league',?,?)",
            [(1, str(TACO_FRANCHISE_ID)), (2, str(WIRE_FRANCHISE_ID))])

    def available_seasons(self):
        return (SnapshotSeason(competition_id=COMPETITION_ID, competition_season_id=SEASON_ID,
            sleeper_league_id="league", season_year=2025, sequence_number=1, role="primary", through_week=8),)

    def completeness_warnings(self):
        return ()

    def resolve_roster_identity(self, roster_key, *, season=None):
        return super().resolve_roster_identity(roster_key)

    def get_week_games_with_players(self, week=None, *, season=None):
        return [{"week": 3, "team_a": "Team Taco", "team_b": "Waiver Wire",
            "points_a": 143.84, "points_b": 116.1, "sleeper_matchup_number": 6}]

    def run_sql(self, query, params=None, *, limit=200):
        cursor = self.connection.execute(query, params or {})
        rows = cursor.fetchmany(limit)
        return {"columns": [c[0] for c in cursor.description], "rows": [tuple(r) for r in rows]}

    def get_transactions(self, week_from, week_to, *, season=None):
        rows = self.connection.execute("""SELECT t.*,tm.*,p.full_name AS player_name,tp.team_name,
            original.team_name AS pick_original_team_name
            FROM transactions t JOIN transaction_moves tm USING(league_id,transaction_id)
            LEFT JOIN players p ON p.player_id=tm.player_id
            JOIN team_profiles tp ON tp.league_id=tm.league_id AND tp.roster_id=tm.roster_id
            LEFT JOIN team_profiles original ON original.league_id=tm.league_id AND original.roster_id=tm.pick_original_roster_id
            WHERE t.week BETWEEN ? AND ?""", (week_from, week_to)).fetchall()
        return _group_transaction_rows([dict(row) for row in rows])

    def add_trade(self, player_id="7543", player_name="Amon-Ra St. Brown", years=(2026, 2027)):
        self.connection.execute("INSERT INTO transactions VALUES ('league','trade1',2,'trade','complete',1757000000000)")
        self.connection.execute("INSERT INTO players VALUES (?,?)", (player_id, player_name))
        transfers = [(0, 2, 1, "player", player_id, None, None, None)]
        transfers.extend((i+1, 1, 2, "pick", None, str(year), 1, 1) for i, year in enumerate(years))
        for index, sender, receiver, kind, player, year, round_, original in transfers:
            for roster, direction in ((sender, "drop" if kind == "player" else "pick_out"),
                                       (receiver, "add" if kind == "player" else "pick_in")):
                self.connection.execute("INSERT INTO transaction_moves VALUES ('league','trade1',?,?,?,?,?,NULL,?,?,?,?,?,NULL)",
                    (index, roster, player, kind, direction, sender, receiver, year, round_, original))


def setup(matches=()):
    registry, context, memory, retrieval, _ = _registered(matches=matches)
    data = SQLiteData()
    adapter = register_memory_tools(registry, memory, data)
    register_datalayer_tools(registry, data)
    return registry, context, memory, retrieval, adapter, data


def saved_source_fact(registry, context, tool="week_games", **arguments):
    executed = registry.get_handler(tool)(**arguments)
    records = context.evidence.records_for(executed.metadata["source"])
    if tool == "week_games":
        record = next(r for r in records if "points_a" in r.fields)
        field = "points_a"
    else:
        record = next(r for r in records if r.fields.get("player_name") and r.perspective == "received")
        field = "player_name"
    binding = {"ref": record.ref, "field": field, "value": record.fields[field]}
    args = {"id": "fact_event", "claim_text": "The selected source event.", "category": "transaction" if tool != "week_games" else "general"}
    # Exercise both the base binding contract and the incoming compact interface.
    if "data_refs" in inspect.signature(save_fact).parameters:
        args["data_refs"] = [record.ref]
        binding.update({key: getattr(record, key) for key in ("subject", "season", "week_from", "week_to", "perspective")})
    result = json.loads(save_fact(context, **args, bindings=[binding]))
    assert result.get("ok", not result.get("error")), result
    assert context.brief.brief.get_fact("fact_event").support_status == "traceable"
    return record


def test_source_fact_resolves_real_matchup_number_not_authored_identifier():
    registry, context, memory, _, _, _ = setup()
    record = saved_source_fact(registry, context, week=3)
    assert record.subject_id.startswith("franchise_")
    result = _call(registry, "save_memory_event", id="event", event_type="matchup",
                   source_fact_ids=["fact_event"], headline="Opening win", summary="Taco won.")
    assert result["saved"] is True
    proposal = memory.proposal_snapshot()[0]
    assert proposal.content.details.sleeper_matchup_id == "6"
    assert proposal.content.details.winner_franchise_id == TACO_FRANCHISE_ID
    assert proposal.content.source_hints["source_fact_ids"] == ["fact_event"]
    rejected = _call(registry, "save_memory_event", id="guessed", event_type="matchup",
        source_fact_ids=["fact_event"], headline="Wrong", summary="Wrong", matchup_id="7-11")
    assert rejected["saved"] is False
    assert "matchup_id" in rejected["error"]["message"]
    assert len(memory.proposal_snapshot()) == 1


@pytest.mark.parametrize("player_id,name,years", [("7543", "Amon-Ra St. Brown", (2026, 2027)),
                                                   ("7611", "Chuba Hubbard", (2026,))])
def test_trade_derives_all_assets_including_natural_pick_identity(player_id, name, years):
    registry, context, memory, _, _, data = setup()
    data.add_trade(player_id, name, years)
    saved_source_fact(registry, context, "transactions", week_from=2, week_to=2)
    result = _call(registry, "save_memory_event", id="trade", event_type="trade",
        source_fact_ids=["fact_event"], headline="Roster bet", summary="A trade worth following.")
    assert result["saved"] is True, result
    proposal = memory.proposal_snapshot()[0]
    assets = proposal.content.details.assets
    assert len(assets) == len(years)+1
    assert assets[0].player_id == player_id
    assert assets[0].direction.value == "receiver_to_sender"
    assert {a.season for a in assets[1:]} == set(years)
    assert all(a.direction.value == "sender_to_receiver" and a.round == 1
               and a.original_franchise_id == TACO_FRANCHISE_ID for a in assets[1:])
    assert proposal.metadata.occurred_at is not None


def storyline_match():
    origin = _event_match().memory
    memory = Storyline(item=origin.item.model_copy(update={"kind": MemoryKind.STORYLINE, "agent_key": "old_arc", "item_id": uuid4()}),
        version=origin.version.model_copy(update={"week": 1}),
        content=StorylineContent.model_validate({"headline": "Early pace", "summary": "The origin.", "status": "active",
            "arc_type": "contender", "salience": 5, "tags": ["contender"],
            "subjects": [{"kind": "franchise", "id": TACO_FRANCHISE_ID, "role": "focus"}],
            "evidence": [{"kind": "event", "version_id": origin.version.version_id, "role": "origin"}],
            "related_storylines": [{"item_id": UUID(int=900), "role": "continuation"}],
            "callback_condition": "Revisit on another strong game", "resolution_summary": "Previous qualification"}))
    return _event_match().model_copy(update={"memory": memory, "week": 1})


def test_recalled_handle_updates_same_item_preserving_origin_and_evidence():
    match = storyline_match()
    registry, context, memory, _, adapter, _ = setup((match,))
    recalled = registry.get_handler("search_memory")(text="pace")
    handle = recalled.result["memories"][0]["memory_handle"]
    assert str(match.memory.item.item_id) not in json.dumps(recalled.result)
    saved_source_fact(registry, context, week=3)
    event = _call(registry, "save_memory_event", id="new_event", event_type="matchup",
        source_fact_ids=["fact_event"], headline="Another win", summary="Taco won.")
    updated = _call(registry, "upsert_storyline_memory_card", update_handle=handle,
        headline="Pace holds", summary="Another supported win.", status="active",
        evidence_event_ids=[event["id"]], origin_week=3)
    assert updated["saved"] is True, updated
    proposal = memory.proposal_snapshot()[-1]
    assert proposal.item_id == match.memory.item.item_id
    assert proposal.expected_item_revision == 7 and proposal.metadata.week == 1
    assert proposal.content.evidence[0] == match.memory.content.evidence[0]
    assert len(proposal.content.evidence) == 2
    assert proposal.content.related_storylines == match.memory.content.related_storylines
    assert proposal.content.callback_condition == match.memory.content.callback_condition
    assert proposal.content.subjects == match.memory.content.subjects
    assert proposal.content.salience == 5 and proposal.content.resolution_summary == "Previous qualification"


def test_failed_event_is_actionable_and_cannot_produce_dependent_card():
    registry, _, memory, _, _, _ = setup()
    error = _call(registry, "save_memory_event", id="bad_event", event_type="trade",
        source_fact_ids=["not_saved"], headline="Trade", summary="Unverified.")
    assert error["error"]["code"] == "insufficient_event_evidence"
    assert "Save the supporting fact first" in error["error"]["message"]
    dependent = _call(registry, "upsert_storyline_memory_card", id="bad_arc", headline="Trade", summary="Unverified.",
        status="active", evidence_event_ids=["bad_event"])
    assert dependent["saved"] is False
    assert "Save or repair those events successfully first" in dependent["error"]["message"]
    assert "do not invent IDs" in dependent["error"]["message"]
    assert not memory.proposal_snapshot()


def test_legacy_pick_serialization_and_complete_natural_identity():
    old = {"kind": "draft_pick", "direction": "sender_to_receiver", "draft_pick_id": str(UUID(int=44))}
    assert DraftPickTradeAsset.model_validate(old).model_dump(mode="json") == old
    output_schema = DraftPickTradeAsset.model_json_schema(mode="serialization")
    assert {"draft_pick_id", "season", "round", "original_franchise_id"} <= set(output_schema["properties"])
    with pytest.raises(ValueError, match="requires draft year"):
        DraftPickTradeAsset.model_validate({"kind": "draft_pick", "direction": "sender_to_receiver", "season": 2026})


def test_omitted_status_and_repeat_hydration_preserve_resolved_card():
    match = storyline_match()
    content = StorylineContent.model_validate({**match.memory.content.model_dump(), "status": "resolved"})
    match = match.model_copy(update={"memory": match.memory.model_copy(update={"content": content})})
    registry, _, memory, _, _, _ = setup((match,))
    first = registry.get_handler("search_memory")(text="pace").result["memories"][0]
    second = registry.get_handler("search_memory")(text="pace").result["memories"][0]
    assert first["memory_handle"] == second["memory_handle"]
    result = _call(registry, "upsert_storyline_memory_card", update_handle=first["memory_handle"],
        headline="Resolved pace", summary="Clarified final wording.")
    assert result["saved"] is True
    assert memory.proposal_snapshot()[0].content.status.value == "resolved"
    assert memory.proposal_snapshot()[0].content.resolution_summary == "Previous qualification"


def test_exact_creation_key_lookup_survives_more_than_100_higher_ranked_items():
    target = storyline_match()
    matches = []
    for index in range(150):
        other = target.memory.model_copy(update={"item": target.memory.item.model_copy(update={
            "item_id": uuid4(), "agent_key": f"newer_{index}"})})
        matches.append(target.model_copy(update={"memory": other, "score": 5}))
    matches.append(target.model_copy(update={"score": 0}))

    class RankedRetrieval(RecordingRetrieval):
        def search(self, *, competition_id, revision_id, request):
            self.calls.append(request)
            visible = self.matches
            if request.query.agent_key is not None:
                visible = tuple(m for m in visible if m.memory.item.agent_key == request.query.agent_key)
            from backend.services.memory import MemoryRetrievalResult
            return MemoryRetrievalResult(competition_id=competition_id, revision_id=revision_id,
                matches=visible[:request.query.limit])

    registry, _, memory, _, adapter, _ = setup()
    retrieval = RankedRetrieval(tuple(matches))
    memory._retrieval = retrieval
    result = _call(registry, "upsert_storyline_memory_card", id="old_arc",
        headline="Existing", summary="A guessed create should not duplicate.")
    assert result["error"]["code"] == "existing_storyline"
    assert retrieval.calls[-1].query.agent_key == "old_arc"
    assert not memory.proposal_snapshot()
    assert "update_handle=memory_1" in result["error"]["message"]


def test_historical_fact_cannot_silently_become_current_season_event():
    registry, context, memory, _, _, _ = setup()
    saved_source_fact(registry, context, week=3)
    memory._competition_season_id = uuid4()
    result = _call(registry, "save_memory_event", id="historical", event_type="matchup",
        source_fact_ids=["fact_event"], headline="Prior season", summary="Historical game.")
    assert "only for its own season" in result["error"]["message"]
    assert not memory.proposal_snapshot()


def test_embedded_trigger_failure_rolls_back_parent_and_allows_repair():
    registry, _, memory, _, _, _ = setup()
    arguments = dict(id="atomic_arc", headline="New arc", summary="Supported arc.")
    failed = _call(registry, "upsert_storyline_memory_card", **arguments,
        trigger_specs=[{"id": "bad_trigger", "trigger_type": "trade_evaluation", "event_id": "missing_event"}])
    assert failed["saved"] is False and failed["error"]["code"] == "unknown_event"
    assert memory.proposal_snapshot() == ()
    repaired = _call(registry, "upsert_storyline_memory_card", **arguments)
    assert repaired["saved"] is True
    assert len(memory.proposal_snapshot()) == 1


def test_entities_only_update_changes_subjects_and_bad_entity_is_actionable():
    match = storyline_match()
    registry, _, memory, _, adapter, _ = setup((match,))
    handle = adapter._presentation.handle_for(match.memory)
    failed = _call(registry, "upsert_storyline_memory_card", update_handle=handle,
        headline="Updated", summary="Updated.", entities=[{"type": "team", "name": "Missing"}])
    assert failed["error"]["code"] == "roster_not_found"
    assert memory.proposal_snapshot() == ()
    success = _call(registry, "upsert_storyline_memory_card", update_handle=handle,
        headline="Updated", summary="Updated.", entities=[{"type": "team", "name": "Waiver Wire"}])
    assert success["saved"] is True
    assert [s.id for s in memory.proposal_snapshot()[0].content.subjects] == [WIRE_FRANCHISE_ID]


def test_cross_season_update_cannot_relabel_origin_week():
    match = storyline_match()
    match = match.model_copy(update={"memory": match.memory.model_copy(update={
        "version": match.memory.version.model_copy(update={"competition_season_id": uuid4()})})})
    registry, _, memory, _, adapter, _ = setup((match,))
    handle = adapter._presentation.handle_for(match.memory)
    result = _call(registry, "upsert_storyline_memory_card", update_handle=handle,
        headline="Updated", summary="Historical arc.")
    assert result["error"]["code"] == "cross_season_update_unsupported"
    assert memory.proposal_snapshot() == ()


def test_event_handle_after_replacement_links_new_version():
    match = _event_match()
    registry, context, memory, _, adapter, _ = setup((match,))
    handle = adapter._presentation.handle_for(match.memory)
    saved_source_fact(registry, context, week=3)
    saved = _call(registry, "save_memory_event", id=match.memory.item.agent_key,
        event_type="matchup", source_fact_ids=["fact_event"], headline="Corrected", summary="Source-derived event.")
    assert saved["saved"] is True
    selected = memory.proposal_snapshot()[0]
    linked = _call(registry, "upsert_storyline_memory_card", id="linked_arc",
        headline="Continuing", summary="New evidence.", evidence_event_ids=[handle])
    assert linked["saved"] is True
    assert memory.proposal_snapshot()[1].content.evidence[0].version_id == selected.version_id
    assert selected.version_id != match.memory.version.version_id


def test_current_season_fact_cannot_replace_prior_season_event_key():
    match = _event_match()
    prior_season_id = UUID(int=2024)
    match = match.model_copy(update={"memory": match.memory.model_copy(update={
        "version": match.memory.version.model_copy(update={
            "competition_season_id": prior_season_id,
        }),
    })})
    registry, context, memory, _, _, _ = setup((match,))
    source = saved_source_fact(registry, context, week=3)
    assert source.season == 2025
    result = _call(registry, "save_memory_event", id=match.memory.item.agent_key,
        event_type="matchup", source_fact_ids=["fact_event"],
        headline="Current result", summary="Current-season source evidence.")
    assert result["saved"] is False
    assert result["error"]["code"] == "cross_season_update_unsupported"
    assert "Use a new event key" in result["error"]["message"]
    assert memory.proposal_snapshot() == ()

    repaired = _call(registry, "save_memory_event", id="matchup_2025_week3",
        event_type="matchup", source_fact_ids=["fact_event"],
        headline="Current result", summary="Current-season source evidence.")
    assert repaired["saved"] is True
    assert memory.proposal_snapshot()[0].operation == "create"
    assert memory.proposal_snapshot()[0].item_id != match.memory.item.item_id


@pytest.mark.parametrize("entity", [
    {"name": "Team Taco", "role": "leader"},
    {"type": "player", "name": "Jahmyr Gibbs"},
    {"type": "unknown", "name": "Team Taco"},
])
def test_unsupported_entities_fail_without_clearing_existing_subjects(entity):
    match = storyline_match()
    registry, _, memory, _, adapter, _ = setup((match,))
    handle = adapter._presentation.handle_for(match.memory)
    failed = _call(registry, "upsert_storyline_memory_card", update_handle=handle,
        headline="Updated", summary="Updated.", entities=[entity])
    assert failed["saved"] is False
    assert failed["error"]["code"] == "unsupported_storyline_entity"
    assert "omit entities to preserve" in failed["error"]["message"]
    assert memory.proposal_snapshot() == ()

    repaired = _call(registry, "upsert_storyline_memory_card", update_handle=handle,
        headline="Updated", summary="Updated.")
    assert repaired["saved"] is True
    assert memory.proposal_snapshot()[0].content.subjects == match.memory.content.subjects


def test_explicit_empty_entities_can_clear_storyline_subjects():
    match = storyline_match()
    registry, _, memory, _, adapter, _ = setup((match,))
    result = _call(registry, "upsert_storyline_memory_card",
        update_handle=adapter._presentation.handle_for(match.memory),
        headline="League-wide arc", summary="The arc now concerns the league.", entities=[])
    assert result["saved"] is True
    assert memory.proposal_snapshot()[0].content.subjects == []
