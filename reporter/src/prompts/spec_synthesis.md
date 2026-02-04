# Spec Synthesis Phase

Your task is to convert the user's request into a complete ReportSpec.

## Process

1. **Classify the Request**
   - Does it match a preset (weekly_recap, power_rankings, team_deep_dive, playoff_reaction)?
   - Is it a partial match with overrides?
   - Is it entirely custom?

2. **Extract Intent**
   - What week(s) should be covered?
   - What tone is requested? (snarky, hype, straight, etc.)
   - Any bias toward or against teams?
   - Specific content requirements?
   - Target length?

3. **Fill the Spec**
   - Start with preset defaults if applicable
   - Apply any explicit overrides from the request
   - Use sensible defaults for unspecified fields

4. **Check Completeness**
   Required fields:
   - article_type
   - time_range (week_start, week_end)

   Material fields (ask if ambiguous):
   - tone_controls
   - bias_profile
   - focus_teams

## Clarifying Questions

If the request is ambiguous on material fields, ask at most 3 questions:

1. **Format**: Weekly recap / Power rankings / Team deep dive / Playoff reaction / Custom
2. **Time Range**: Week N / Weeks N-M / Full season
3. **Tone**: Straight sportswriter / Hype & celebratory / Snarky roast-light / Savage roast
4. **Bias** (if mentioned): Favor [teams] / Roast [teams] / Intensity 1-3
5. **Length**: Short (~500w) / Medium (~1000w) / Long (~1500w)

Always provide defaults inline: "Tone: hype (default: straight sportswriter)"

## Example Spec Extraction

Request: "Write a snarky recap of Week 8 favoring Team Taco"

Extracted:
- article_type: weekly_recap (preset match)
- time_range: week 8 only
- tone_controls: {snark_level: 2, hype_level: 1}
- bias_profile: {favored_teams: ["Team Taco"], intensity: 2}
- length: default (1000w)

## Output

Return a complete ReportSpec JSON object. If you asked clarifying questions, wait for answers before finalizing.
