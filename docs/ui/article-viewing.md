# Article Viewing Experience

## Purpose

The Articles area is the reading surface for finished work. Its default state
must help a league member find and read an article without confronting the
machinery that produced it. Generation settings, artifacts, execution traces,
and usage remain available to the operator, but they are supporting evidence,
not peer content.

This contract applies to two related surfaces:

- the **article library**, where readers discover submitted articles; and
- the **article reader**, where one exact submitted version is read.

Pending, failed, and cancelled runs are not articles. They retain the existing
operations-first generation page.

## Information Priority

The UI uses four priority levels. Higher levels must not be displaced by lower
levels on initial load.

| Priority | Information | Presentation rule |
| --- | --- | --- |
| 1. Reading | Article title, optional preview/dek, exact article body | Dominates the viewport and reading order |
| 2. Context | League, season, week range, completion date, historical-backtest disclosure | Compact masthead and library-card metadata |
| 3. Reader actions | Back to library, previous/next article, Copy Markdown, Generate another | Available near the article without interrupting it |
| 4. Production evidence | Assignment, model chain, snapshot, memory input, hashes, artifacts, execution, token usage, estimated cost, rerun/edit controls | Hidden behind `Behind this article` / `Run details` by default |

The live/backtest distinction is contextual truth, not general telemetry. A
historical backtest must be visibly labeled in both the library and reader. A
normal live article may use a quieter label.

The assignment is not the article summary. Until the API exposes a preview
derived from submitted content, request text may be used as a clearly
identified fallback, but it must not visually compete with the headline.

## Page Model

### Article library

Route: `/competitions/:competitionId/articles`

The library is an editorial archive, not a generation-usage table.

1. A compact page masthead contains `Articles`, the competition context, and
   `Generate article`.
2. Season and mode filters occupy one compact toolbar. Filters remain in the
   URL and the latest applicable article is selected after filtering. Week
   filtering may join the toolbar when the API supports it.
3. The newest matching article is a featured story with headline, preview,
   season/week, completion date, mode disclosure, and `Read article`.
4. Remaining results appear in a headline-led vertical list. Each item shows
   headline, preview, season/week, date, and historical disclosure.
5. Model, token, cost, hash, rerun, and workspace fields do not appear in the
   default library. They remain available from the article's run details.
6. Pagination stays at the end of the archive. Empty and error states retain a
   clear route to generate an article or clear filters.

The wide-screen default is a featured article followed by a two-column archive
only when cards remain comfortably readable. A single vertical list is the
baseline and the mobile layout.

### Article reader

Canonical route:
`/competitions/:competitionId/articles/:generationId`

The existing generation route remains canonical for non-submitted runs and for
operational inspection. Existing successful-generation article links may
redirect to or render the canonical reader so bookmarks remain valid.

The reader is ordered as follows:

1. A quiet breadcrumb/back action returns to the filtered article library.
2. The article masthead shows mode/category, headline, optional preview,
   league/season/week, and completion date.
3. A small action group offers `Copy Markdown` and `Behind this article`.
4. The exact submitted Markdown renders immediately below the masthead in a
   centered reading column of roughly 68–76 characters.
5. Previous and next submitted articles provide chronological navigation at
   the end of the body.
6. A compact footer offers `Generate another article`.

On large screens, the body remains the visual center. Reader context may occupy
a narrow rail only when it does not reduce the prose below the target reading
measure. On smaller screens, all content is one column and the production
evidence opens as a full-height sheet or an in-flow disclosure.

### Behind this article

`Behind this article` is the bridge from reading to operations. It opens a
secondary surface rather than inserting a full run dashboard before the body.
It contains:

- a concise Overview: assignment, mode, model chain, snapshot, memory input,
  completion time, and rerun/edit actions;
- Artifacts;
- Execution; and
- Usage.

Hashes, opaque IDs, artifact paths, and manifests are shown only inside this
surface and only where they support verification. The existing detail panels
remain reusable; the redesign changes their hierarchy and entry point, not the
truth they display.

### Active and unsuccessful runs

Pending and running generations keep the progress-first page with stage, turn,
elapsed time, assignment, and execution. Failed or cancelled generations keep
failure recovery and rerun/edit actions prominent. The UI must never present
these states as empty or partially available articles.

## Responsive and Accessibility Contract

- Article content precedes secondary evidence in DOM and visual order.
- Headline links have descriptive accessible names; entire cards are not
  nested interactive click targets.
- Filter state, library page, and selected article remain deep-linkable.
- Returning from the reader restores the prior filters and page when browser
  history is available.
- The reading column has no horizontal overflow; Markdown tables keep their
  existing independently scrollable region.
- Opening and closing run details preserves focus. The sheet/disclosure is
  keyboard reachable and labeled by its article title.
- Historical-backtest meaning is communicated with text, not color alone.
- Loading uses stable article-shaped skeletons. A reader error does not expose
  an empty run-audit shell as if the article loaded successfully.

## Data and Route Contract

The first implementation can use the existing article list and exact submitted
article endpoints. To support a true editorial library, `ArticleSummary` should
later add:

- `preview: str | None`, derived from the first useful prose paragraph in the
  exact submitted Markdown after removing headings and formatting; and
- optionally a stable article category if category becomes a reporter output
  contract rather than an inference from assignment text.

The frontend must not fetch every full artifact to construct previews. Until
`preview` exists, it should label request text as `Assignment` or omit the
preview rather than implying it was extracted from the article.

Previous/next navigation may initially use the current filtered article page.
If the library becomes large or direct-reader navigation must cross page
boundaries, add a server-owned adjacent-article projection rather than loading
unbounded history.

## Layout Sketches

Wide article library:

```text
Articles                                      [Generate article]
[Season] [Live / Backtest]

LATEST
Large headline
Article preview or labeled Assignment fallback
2026 · Week 8 · Aug 26                         [Read article]

MORE ARTICLES
Headline + preview + season/week/date          [Read]
Headline + preview + season/week/date          [Read]
                                               [Previous] [Next]
```

Wide article reader:

```text
< Back to articles

BACKTEST · 2026 · WEEK 8 · AUG 26
Article headline
Optional article-derived preview
                              [Copy Markdown] [Behind this article]

                 Exact submitted article body
                 in a centered reading column

< Previous article                         Next article >
```

`Behind this article` opens as a right-side sheet on wide screens and a
full-height sheet or in-flow disclosure on narrow screens. It contains
Overview, Artifacts, Execution, and Usage without moving the reader's scroll
position.

## Implementation Sequence

1. **Reader first:** add the submitted-article route and layout, reuse the exact
   article query/Markdown renderer, and move existing audit panels behind the
   secondary disclosure. Preserve successful generation links through redirect
   or compatibility rendering.
2. **Library second:** replace the operational table with a featured latest
   story and headline-led archive while retaining URL-backed filters, paging,
   and current loading/error/empty behavior.
3. **Preview quality:** optionally add `ArticleSummary.preview` on the backend
   and generated client contract. The first two slices can ship with a labeled
   Assignment fallback.
4. **Acceptance:** run the existing frontend format, lint, typecheck, and build
   gates once, then manually verify direct links, browser history, filters,
   paging, keyboard/focus behavior, 375 px layout, and every generation state.

## Acceptance Coverage

- The first viewport of a successful reader contains the headline and the
  beginning of the article body at ordinary desktop and mobile sizes.
- No assignment card, run-metadata card, success banner, or audit-tab header
  appears before the article body.
- The library can be understood from headlines, article context, and previews
  without model or cost knowledge.
- Backtests are clearly distinguishable from live articles.
- Copy Markdown uses the exact submitted version.
- Run details remain reachable in one action and preserve all existing audit
  capabilities.
- Pending, failed, and cancelled generations keep truthful operations-first
  behavior.
- Direct links, browser back, filters, pagination, keyboard use, and 375 px
  layouts are manually verified without console errors.

## Non-goals

- public publishing, sharing, comments, reactions, or readership analytics;
- rich-text or Markdown editing;
- generated hero images;
- replacing durable generation, artifact, execution, or usage contracts; and
- presenting generation cost or model telemetry as reader-facing article
  quality signals.
