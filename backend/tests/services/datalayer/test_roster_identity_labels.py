"""Frozen, whole-label identity matching; no model or mutable source calls."""
from __future__ import annotations

import sqlite3
from uuid import UUID

import pytest

from backend.services.datalayer.query.identity import resolve_roster_identity


COMPETITION = UUID(int=1)
SEASON = UUID(int=2)


@pytest.fixture
def identities():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE roster_identities(competition_id TEXT, competition_season_id TEXT,
            season_roster_id TEXT, franchise_id TEXT, roster_id INTEGER, league_id TEXT);
        CREATE TABLE team_profiles(league_id TEXT, roster_id INTEGER, team_name TEXT, manager_name TEXT);
    """)
    for roster, label, manager in ((1, "FANTASY IS LUCK🤬🤬🤬", "Alice🔥"), (2, "Lebron James", "Bob")):
        connection.execute("INSERT INTO roster_identities VALUES(?,?,?,?,?,?)",
            (str(COMPETITION), str(SEASON), str(UUID(int=100+roster)), str(UUID(int=200+roster)), roster, "league"))
        connection.execute("INSERT INTO team_profiles VALUES(?,?,?,?)", ("league", roster, label, manager))
    yield connection
    connection.close()


def resolve(connection, key):
    return resolve_roster_identity(connection, competition_id=COMPETITION,
        competition_season_id=SEASON, league_id="league", roster_key=key)


def test_actual_wrong_emoji_resolves_both_explicit_team_relationships(identities):
    before = tuple(identities.iterdump())
    fantasy = resolve(identities, "FANTASY IS LUCK🥶🥶🥶")
    lebron = resolve(identities, "Lebron James")
    assert fantasy.status == lebron.status == "resolved"
    assert [fantasy.identity.franchise_id, lebron.identity.franchise_id] == [UUID(int=201), UUID(int=202)]
    assert fantasy.identity.team_name == "FANTASY IS LUCK🤬🤬🤬"
    assert tuple(identities.iterdump()) == before


def test_decorative_label_ambiguity_preserves_exact_precedence(identities):
    identities.execute("UPDATE team_profiles SET team_name=? WHERE roster_id=2", ("FANTASY IS LUCK🔥",))
    ambiguous = resolve(identities, "FANTASY IS LUCK🥶")
    assert ambiguous.status == "ambiguous"
    assert len(ambiguous.matches) == 2
    assert resolve(identities, "FANTASY IS LUCK🤬🤬🤬").identity.franchise_id == UUID(int=201)
    assert resolve(identities, "2").identity.franchise_id == UUID(int=202)
    assert resolve(identities, str(UUID(int=101))).identity.franchise_id == UUID(int=201)


@pytest.mark.parametrize("key", ["FANTASY", "FANTASY IS LUCK!🥶", "FANTASYISLUCK", "Alice🥶", "🥶", "01"])
def test_no_fuzzy_punctuation_manager_or_invalid_identity_fallback(identities, key):
    assert resolve(identities, key).status == "not_found"


def test_fallback_never_crosses_selected_frozen_season(identities):
    identities.execute("INSERT INTO roster_identities VALUES(?,?,?,?,?,?)",
        (str(COMPETITION), str(UUID(int=3)), str(UUID(int=103)), str(UUID(int=203)), 3, "league"))
    identities.execute("INSERT INTO team_profiles VALUES(?,?,?,?)", ("league", 3, "FANTASY IS LUCK🥶", "Carol"))
    assert resolve(identities, "FANTASY IS LUCK🥶").identity.franchise_id == UUID(int=201)
    assert resolve(identities, "Alice🔥").identity.franchise_id == UUID(int=201)
