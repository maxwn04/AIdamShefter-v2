"""Load pipeline: fetch → normalize → store into a SQLite engine.

Contract: owns orchestration only. Does not expose curated query APIs.
Callers (SleeperLeagueData) open the query connection after load returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.engine import Connection, Engine

from .normalize import (
    apply_traded_picks,
    derive_games,
    derive_team_profiles,
    normalize_bracket,
    normalize_league,
    normalize_matchups,
    normalize_players,
    normalize_roster_players,
    normalize_rosters,
    normalize_standings,
    normalize_transaction_moves,
    normalize_transactions,
    normalize_users,
    seed_draft_picks,
)
from .schema import SeasonContext, StandingsWeek
from .sleeper_api import (
    SleeperClient,
    get_league,
    get_league_rosters,
    get_league_users,
    get_losers_bracket,
    get_matchups,
    get_players,
    get_state,
    get_traded_picks,
    get_transactions as api_get_transactions,
    get_winners_bracket,
)
from .store.sqlite_store import bulk_insert, create_tables


@dataclass(frozen=True)
class LoadResult:
    """Metadata produced by a successful league load."""

    league_id: str
    season: str
    computed_week: int
    effective_week: int
    week_override: int | None


def _record_string_to_weeks(
    record_string: str | None,
    *,
    chars_per_week: int,
) -> list[tuple[int, int, int, int]]:
    if not record_string:
        return []
    trimmed = "".join(ch for ch in record_string.strip().upper() if ch.strip())
    if not trimmed:
        return []
    week_count = len(trimmed) // chars_per_week
    results: list[tuple[int, int, int, int]] = []
    wins = 0
    losses = 0
    ties = 0
    for week in range(1, week_count + 1):
        end_idx = week * chars_per_week
        slice_value = trimmed[end_idx - chars_per_week : end_idx]
        for outcome in slice_value:
            if outcome == "W":
                wins += 1
            elif outcome == "L":
                losses += 1
            elif outcome == "T":
                ties += 1
        results.append((week, wins, losses, ties))
    return results


def _insert_rows(conn: Connection, rows: list) -> None:
    if rows:
        bulk_insert(conn, rows[0].table_name, rows)


def load_league(
    engine: Engine,
    *,
    client: SleeperClient,
    league_id: str,
    week_override: int | None = None,
) -> LoadResult:
    """Fetch Sleeper data, normalize, and populate ``engine`` from scratch."""
    raw_league = get_league(league_id, client=client)
    raw_users = get_league_users(league_id, client=client)
    raw_rosters = get_league_rosters(league_id, client=client)
    raw_state = get_state("nfl", client=client)

    league = normalize_league(raw_league)
    users = normalize_users(raw_users)
    rosters = normalize_rosters(raw_rosters, league_id=league_id)
    roster_players = normalize_roster_players(raw_rosters, league_id=league_id)
    team_profiles = derive_team_profiles(
        raw_rosters, raw_users, league_id=league_id
    )

    with engine.begin() as conn:
        create_tables(conn)

        bulk_insert(conn, league.table_name, [league])
        _insert_rows(conn, users)
        _insert_rows(conn, rosters)
        _insert_rows(conn, team_profiles)

        draft_rounds = int(
            (raw_league.get("settings") or {}).get("draft_rounds") or 0
        )
        draft_picks = seed_draft_picks(
            rosters, league_id, league.season, draft_rounds
        )
        _insert_rows(conn, draft_picks)

        raw_traded_picks = get_traded_picks(league_id, client=client)
        apply_traded_picks(conn, raw_traded_picks, league_id)

        raw_players = get_players("nfl", client=client)
        players = normalize_players(raw_players)
        _insert_rows(conn, players)
        _insert_rows(conn, roster_players)

        computed_week = int(raw_state.get("week") or 0)
        effective_week = int(week_override or computed_week or 0)
        season = str(raw_league.get("season") or raw_state.get("season") or "")
        league_average_match = (
            int((raw_league.get("settings") or {}).get("league_average_match") or 0)
            if raw_league.get("settings") is not None
            else 0
        )
        chars_per_week = 2 if league_average_match == 1 else 1

        playoff_week_start = (
            int(league.playoff_week_start)
            if league.playoff_week_start is not None
            else None
        )

        if effective_week > 0:
            for week in range(1, effective_week + 1):
                raw_matchups = get_matchups(league_id, week, client=client)
                matchup_rows, player_performances = normalize_matchups(
                    raw_matchups,
                    league_id=league_id,
                    season=season,
                    week=week,
                )
                is_playoffs = (
                    playoff_week_start is not None
                    and week >= int(playoff_week_start)
                )
                games = derive_games(matchup_rows, is_playoffs=is_playoffs)
                _insert_rows(conn, matchup_rows)
                _insert_rows(conn, player_performances)
                _insert_rows(conn, games)

                raw_transactions = api_get_transactions(
                    league_id, week, client=client
                )
                transactions = normalize_transactions(
                    raw_transactions,
                    league_id=league_id,
                    season=season,
                    week=week,
                )
                moves = normalize_transaction_moves(raw_transactions)
                _insert_rows(conn, transactions)
                _insert_rows(conn, moves)

            record_standings: list[StandingsWeek] = []
            record_weeks: set[int] = set()

            for raw_roster in raw_rosters:
                roster_id = int(raw_roster["roster_id"])
                record_string = (raw_roster.get("metadata") or {}).get("record")
                if isinstance(record_string, list):
                    record_string = "".join(
                        str(item) for item in record_string if item
                    )
                if isinstance(record_string, str):
                    for week, wins, losses, ties in _record_string_to_weeks(
                        record_string, chars_per_week=chars_per_week
                    ):
                        if week > effective_week:
                            break
                        if (
                            playoff_week_start is not None
                            and week >= playoff_week_start
                        ):
                            continue
                        record_standings.append(
                            StandingsWeek(
                                league_id=league_id,
                                season=season,
                                week=int(week),
                                roster_id=roster_id,
                                wins=wins,
                                losses=losses,
                                ties=ties,
                                points_for=0.0,
                                points_against=0.0,
                                rank=None,
                                streak_type=None,
                                streak_len=None,
                            )
                        )
                        record_weeks.add(int(week))

            _insert_rows(conn, record_standings)

            should_insert_current = False
            if not record_weeks:
                should_insert_current = True
            elif effective_week > max(record_weeks):
                if (
                    playoff_week_start is None
                    or effective_week < playoff_week_start
                ):
                    should_insert_current = True

            if should_insert_current:
                standings = normalize_standings(
                    raw_rosters,
                    league_id=league_id,
                    season=season,
                    week=effective_week,
                )
                _insert_rows(conn, standings)

        # Only load playoff brackets if we've reached the playoff weeks.
        # Loading them earlier would leak future results when using
        # week_override to view a mid-season snapshot.
        should_load_brackets = (
            playoff_week_start is None or effective_week >= playoff_week_start
        )
        if should_load_brackets:
            raw_winners = get_winners_bracket(league_id, client=client)
            raw_losers = get_losers_bracket(league_id, client=client)
            winners = normalize_bracket(
                raw_winners,
                league_id=league_id,
                season=season,
                bracket_type="winners",
            )
            losers = normalize_bracket(
                raw_losers,
                league_id=league_id,
                season=season,
                bracket_type="losers",
            )
            _insert_rows(conn, winners)
            _insert_rows(conn, losers)

        season_context = SeasonContext(
            league_id=league_id,
            computed_week=computed_week,
            override_week=week_override,
            effective_week=effective_week,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        bulk_insert(conn, season_context.table_name, [season_context])

    return LoadResult(
        league_id=league_id,
        season=season,
        computed_week=computed_week,
        effective_week=effective_week,
        week_override=week_override,
    )
