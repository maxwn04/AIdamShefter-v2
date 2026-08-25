# Frontend Architecture

## Stack Decision

The frontend is a standalone TypeScript application under `frontend/`:

| Concern | Choice |
| --- | --- |
| Runtime | Node.js 22.22.x |
| Package manager | `pnpm` with `packageManager` pinned in `package.json` and `pnpm-lock.yaml` committed |
| Build/dev server | Vite |
| UI runtime | React + TypeScript in strict mode |
| Routing | React Router with route-level lazy loading |
| Component system | Radix-backed shadcn/ui components stored in the repository, Tailwind CSS, accessible primitives |
| Server state | TanStack Query |
| Forms | React Hook Form + Zod form schemas |
| HTTP contracts | FastAPI OpenAPI -> `openapi-typescript` types + a small typed fetch client |
| Tables | TanStack Table only where sorting/filtering/table behavior is needed |
| Markdown | `react-markdown` + GFM; raw HTML disabled |
| Frontend automated tests | Deferred until the UI stabilizes or regressions justify them |
| Formatting/linting | Prettier + ESLint with type-aware rules |

Vite is appropriate because this is an authenticated/local product console, not
an SEO-dependent publishing site. Server rendering would add a deployment and
data-loading model without helping the initial journeys. The backend remains a
separately runnable FastAPI process.

TanStack Query owns remote state and polling. React context is limited to app
shell concerns such as the active competition and theme. Do not add Redux or a
generic client store for API resources.

## Package Layout

```text
frontend/
├── package.json
├── pnpm-lock.yaml
├── components.json
├── index.html
├── vite.config.ts
├── tsconfig.json
├── eslint.config.js
├── src/
│   ├── app/
│   │   ├── router.tsx
│   │   ├── providers.tsx
│   │   ├── shell.tsx
│   │   └── query-client.ts
│   ├── api/
│   │   ├── generated/schema.d.ts
│   │   ├── client.ts
│   │   ├── errors.ts
│   │   └── query-keys.ts
│   ├── components/
│   │   ├── ui/
│   │   └── shared/
│   ├── features/
│   │   ├── competitions/
│   │   ├── seasons/
│   │   ├── refreshes/
│   │   ├── generations/
│   │   ├── articles/
│   │   ├── artifacts/
│   │   ├── execution/
│   │   └── usage/
│   ├── routes/
│   ├── lib/
│   │   ├── date-time.ts
│   │   ├── money.ts
│   │   └── markdown.tsx
│   ├── main.tsx
│   └── index.css
```

Using `src/` as the application source root is the conventional Vite/React
layout. It keeps application modules separate from package metadata, build
configuration, generated output, and future operational files. The
feature-oriented folders inside `src/` are also a common scaling pattern: code
is grouped by product capability while low-level shadcn components and shared
infrastructure remain easy to find.

The tree is a target shape, not a requirement to scaffold every directory on
day one. Create `app`, `api`, `components/ui`, and the first active feature and
route; add later feature folders only when their implementation begins.

Feature folders contain feature-specific components, query/mutation hooks,
form schemas, and presentation helpers. `components/ui` contains only shadcn
source components; product logic does not accumulate there. Route modules
compose features and own route parameters, error boundaries, and page layout.

## API Type Workflow

FastAPI's OpenAPI output is the source of transport truth. A deterministic
script generates `src/api/generated/schema.d.ts`; CI regenerates and fails on a
diff so backend contract changes cannot silently bypass frontend review.

Generated files contain types only. A hand-written client owns:

- base URL and Vite development proxy behavior;
- JSON parsing;
- typed error normalization;
- correlation headers;
- request cancellation via `AbortSignal`; and
- the small set of call helpers used by feature hooks.

Do not duplicate complete API response interfaces by hand. Zod schemas remain
appropriate for form state because form inputs have UI-specific coercion and
cross-field validation that differ from wire types.

Development proxies `/api` and health requests to the local FastAPI port. The
production hosting decision should preserve same-origin `/api` when possible;
otherwise the backend needs an explicit allowlisted CORS configuration rather
than `*`.

## Server State and Polling

Query keys are factories rooted by competition:

```text
competitions.list(filters)
competitions.detail(competitionId)
seasons.list(competitionId)
refreshes.list(competitionId, seasonId, page)
generations.list(competitionId, filters, page)
generations.detail(competitionId, generationId)
generations.article(competitionId, generationId)
generations.aiCalls(competitionId, generationId, page)
generations.toolCalls(competitionId, generationId, page)
generations.artifacts(competitionId, generationId, page)
generations.usage(competitionId, generationId)
```

Generation detail polls while status is `pending` or `running`, pauses when the
document is hidden/offline, and stops at a terminal state. Child telemetry is
refetched on stage/turn changes or when its tab is open; do not poll every
large tool result on the article tab. Refresh mutation invalidates season,
refresh-history, competition-summary, and relevant generation-readiness keys.

Mutations use server-returned resources and targeted invalidation. Optimistic
updates are reserved for reversible presentation changes; competition creation,
refresh, generation, promotion, and discard wait for server confirmation.

## Form Model

`GenerationFormValues` is UI-specific and maps once to
`SubmitGenerationBody`. Important transformations are explicit:

- mode -> `kind`;
- tags/chips -> ordered string arrays;
- slider/display values -> integer control levels;
- empty optional bias -> `null`/omitted according to the API;
- ordered fallback rows -> `settings.model.fallback_models`; and
- advanced defaults -> complete settings accepted by the backend.

Validate week order and model-chain uniqueness in the form for immediate
feedback, while treating server validation as authoritative. Preserve dirty
form state during a refresh detour and before navigating away.

## Design System Direction

The visual language should feel like an editorial operations desk: high
information density, readable long-form typography, restrained status color,
and clear separation between the article and its machinery. Avoid a grid of
decorative KPI cards when a compact list or metadata rail communicates more.

Initial shadcn components likely include button, input, textarea, select,
combobox/command, dialog, sheet, tabs, table, badge, alert, skeleton, tooltip,
popover, dropdown menu, accordion/collapsible, separator, slider, checkbox,
toast/sonner, and sidebar/breadcrumb. Components are added only as pages need
them so local source remains reviewable.

Use a prose style for rendered Markdown that is independent from compact
operator typography. Raw HTML is disabled, external links are visibly marked,
and code/JSON areas wrap or scroll without changing the page width.

## Frontend Verification Policy

Automated frontend tests are deferred for the initial implementation. The UI is
still being discovered, so component snapshots, mocked API tests, and a browser
suite would create maintenance cost while page structure and interactions are
changing quickly.

Each frontend layer instead has four required checks:

1. strict TypeScript compilation;
2. lint and formatting checks;
3. a successful production build; and
4. a short manual acceptance pass through the affected journey against the real
   local backend.

The manual pass is recorded in `.context/ui/log.md`, including the route,
important states checked, and any known limitations. New backend resources and
workflow invariants still receive targeted backend tests under `backend/tests`;
the deferral applies only to frontend automated tests.

Frontend tests can be introduced later where evidence makes them valuable—for
example, a repeatedly broken generation-form mapping, polling lifecycle, cost
calculation presentation, or canonical-memory promotion flow. No test framework
is installed preemptively.

## Delivery and Quality Gates

The frontend has scripts for `dev`, `build`, `typecheck`, `lint`,
`format:check`, and `api:generate`. Root documentation may provide convenience
commands, but JavaScript dependencies and the lockfile remain under `frontend/`.

CI uses the pnpm version pinned by the `packageManager` field, installs with
`pnpm install --frozen-lockfile`, checks generated API drift, then runs format,
lint, typecheck, and the production build.

Initial performance goals are pragmatic: route-level code splitting, no eager
loading of artifact/call bodies, bounded list pages, and responsive interaction
on ordinary league histories. Manual acceptance includes accessibility checks
for dialogs, tabs, navigation, form errors, keyboard focus, and status updates
until automated accessibility checks are justified.

## Deferred Choices

- frontend hosting and FastAPI static-asset ownership;
- authentication/session transport;
- websocket or server-sent progress;
- rich-text article editing;
- public article rendering/SEO;
- multi-competition analytics;
- a shared JavaScript monorepo/package layer; and
- frontend unit, component, and browser test infrastructure.

None is required to scaffold the top-level `frontend/` application or complete
the three initial journeys.
