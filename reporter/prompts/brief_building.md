# Brief Building Phase (Research)

Your task is to research the league data and build a ReportBrief that will drive the article.

## Research Strategy

### For Weekly Recap
1. Start with `league_snapshot(week=N)` for comprehensive week data
2. Call `week_player_leaderboard(week=N, limit=10)` for top performers
3. For standout games, use `team_game(roster_key, week=N)`
4. Check `transactions(week_from=N, week_to=N)` for roster moves

### For Power Rankings
1. Get `league_snapshot(week=N)` for current standings
2. For each team: `team_dossier(roster_key)` for recent performance
3. Optionally: `transactions(week_from, week_to)` for roster moves context

### For Team Deep Dive
1. `team_dossier(roster_key, week=N)` for comprehensive profile
2. `team_schedule(roster_key)` for full season arc
3. `roster_current(roster_key)` for roster analysis
4. `team_transactions(roster_key, 1, N)` for all roster moves

### For Playoff Reaction
1. `week_games(week=playoff_week)` for matchup results with player breakdowns
2. `team_dossier(winner_roster_key)` for champion profile

## Building Facts

For each relevant data point, create a Fact:

```json
{
  "id": "fact_001",
  "claim_text": "Team Taco defeated The Waiver Wire 142.3-98.7 in Week 8",
  "data_refs": ["league_snapshot:week=8"],
  "numbers": {"team_score": 142.3, "opponent_score": 98.7, "week": 8},
  "category": "score"
}
```

Categories:
- `score`: Game scores and outcomes
- `standing`: Records, rankings, playoff positioning
- `transaction`: Trades, waivers, FA pickups
- `player`: Individual player performances
- `streak`: Win/loss streaks
- `general`: Other relevant facts

## Identifying Storylines

Look for narratives in the data:
- **Upsets**: Lower-ranked team beats higher-ranked
- **Blowouts**: Dominant victories (30+ point margin)
- **Nail-biters**: Games decided by < 5 points
- **Hot streaks**: Teams on 3+ game win streaks
- **Cold streaks**: Teams on 3+ game losing streaks
- **Comeback**: Team rebounds from previous loss
- **Big trades**: Significant roster moves
- **Breakout performances**: Player exceeds expectations
- **Injuries/Duds**: Key players underperforming

For each storyline:
```json
{
  "id": "story_001",
  "headline": "Taco Tuesday Massacre",
  "summary": "Team Taco dominated The Waiver Wire with a 43-point victory, their largest margin of the season.",
  "supporting_fact_ids": ["fact_001", "fact_005"],
  "priority": 1,
  "tags": ["blowout", "season_high"]
}
```

## Creating the Outline

Based on the ReportSpec structure and identified storylines:

```json
{
  "title": "Introduction",
  "bullet_points": [
    "Hook with lead storyline",
    "Week N summary statement",
    "Tease key matchups"
  ],
  "required_fact_ids": ["fact_001"],
  "storyline_ids": ["story_001"]
}
```

## Output

Return a complete ReportBrief with:
- meta: League info and article metadata
- facts: All verified facts (aim for 10-20 for weekly recap)
- storylines: 3-6 identified narratives
- outline: Section plan matching the spec structure
- style: Resolved from spec
- bias: Resolved from spec
