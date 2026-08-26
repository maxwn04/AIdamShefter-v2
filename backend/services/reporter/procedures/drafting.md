# Drafting Procedure

Use this procedure for sustained composition and revision of the publishable article. Draft from verified material, but allow the act of writing to expose evidence gaps and better storylines. Resolve narrow gaps directly; substantial discoveries may lead back into deeper research or storyline mining.

## Operating Rules

- The brief is the source of factual truth. Saved storylines and the outline are revisable planning aids, not immutable constraints.
- Treat verified callbacks in the brief as grounded material, but still name the old event and current payoff in prose.
- Do not invent scores, records, player points, transaction details, standings, injuries, or playoff scenarios.
- Numeric claims must match the numbers or claim text recorded in the brief.
- Treat the outline as a working plan, not a constraint. Preserve it when it remains useful; update supported framing directly when drafting reveals a better structure. Load `storyline` only for substantial narrative rethinking.
- For a narrow missing fact, make the targeted datalayer call, record the verified result in the brief, and resume drafting. Load `research` only when the gap requires broad exploration.
- Continue mining storylines while writing. A strong paragraph may reveal a callback, reversal, or future memory worth researching or proposing.
- Draft with `create_artifact` at your chosen article path when the article does not exist. Use the same path and revision-checked `edit_artifact` calls for subsequent changes.
- Do not submit until you have performed a claim-level verification pass, whether or not you load the dedicated verification procedure.

## Drafting Flow

1. Read `research_brief.md` when its current content is not already available.
2. Identify the strongest supported lead and draft the sections with the clearest evidence first.
3. After meaningful additions, ask whether the prose exposed a factual gap, a weak storyline, or a stronger callback. Resolve only the gaps that matter to the article.
4. Create a coherent Markdown draft at one stable path, or continue from the current draft content and revision.
5. Read an artifact again only when its current state is unknown or when a full-document review is needed.
6. Use exact `edit_artifact` replacements for local improvements. For a full rewrite, replace the complete current content using its current revision.
7. When the draft is complete, perform a claim-level audit. Load `verification` if its detailed checklist would improve that audit.

## Writing Standards

- Open with the best material, not a generic recap sentence.
- Use concrete details from facts rather than vague claims.
- Prioritize priority-1 storylines, then priority-2 storylines, then quick hits.
- For callback paragraphs, clearly state what happened then, what happened now, and why the meaning changed.
- Do not use vague continuity phrases such as "this has been brewing," "the storyline continues," or "it came full circle" unless the paragraph names the old event and the new payoff.
- Keep paragraphs focused. Standard sections should usually be 2-5 paragraphs.
- Use Markdown:
  - `#` for the headline.
  - `##` for major section headings.
  - `**bold**` for emphasis when useful.
- Match the requested target length. As a practical guide:
  - 500 words: 1-2 storylines.
  - 1000 words: 3-4 storylines.
  - 1500+ words: broader weekly coverage or deeper analysis.

## Voice And Bias

Apply the recorded style consistently:

- Sports columnist: informed, sharp, and personable.
- Snarky columnist: witty and irreverent, with playful jabs.
- Hype broadcaster: high energy, dramatic, and celebratory.
- Beat reporter: factual, measured, and analysis-heavy.
- Custom voices: satisfy the user's request while preserving factual grounding.

Apply bias as framing only:

- Favored teams can get more enthusiastic language, more prominent placement, and more charitable framing.
- Disfavored teams can get skepticism or playful roasting.
- The score, record, ranking, transaction, and player points must remain exactly what the facts say.

## Section Organization

Use stable, descriptive Markdown headings for article sections, such as:

- Headline and lead
- Lead story
- Standings shift
- Quick hits
- Transactions
- Playoff picture
- Closing

Before submission, make sure each required outline fact appears in the article and the document has a coherent opening, body, and close.
