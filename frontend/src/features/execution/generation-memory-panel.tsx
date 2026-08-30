import {
  BrainCircuit,
  CircleAlert,
  LoaderCircle,
  Save,
  Search,
} from "lucide-react";

import { ApiError } from "@/api/errors";
import { DateTime } from "@/components/shared/date-time";
import { StructuredContentViewer } from "@/components/shared/structured-content-viewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  GenerationMemoryRecall,
  ToolCall,
} from "@/features/execution/api";
import {
  useGenerationMemoryRecall,
  useGenerationMemoryToolCalls,
} from "@/features/execution/queries";

interface GenerationMemoryPanelProps {
  competitionId: string;
  generationId: string;
  active: boolean;
  generationActive: boolean;
  automaticRecallEnabled: boolean;
}

type MemoryKind = "storyline" | "fact" | "event" | "trigger" | "context_note";

interface SavedMemory {
  key: string;
  kind: MemoryKind;
  operation: "create" | "replace" | "unknown";
  arguments: Record<string, unknown>;
}

const memoryKinds: readonly MemoryKind[] = [
  "storyline",
  "fact",
  "event",
  "trigger",
  "context_note",
];

const writeKinds: Readonly<Record<string, MemoryKind>> = {
  save_memory_event: "event",
  upsert_storyline_memory_card: "storyline",
  save_storyline_trigger: "trigger",
  save_team_context: "context_note",
  save_league_note: "context_note",
};

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const parsed = record(item);
        return parsed ? [parsed] : [];
      })
    : [];
}

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0
    ? value
    : undefined;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}

function memoryKind(value: unknown): MemoryKind | undefined {
  return memoryKinds.find((kind) => kind === value);
}

function titleCase(value: string): string {
  return value
    .split(/[_\-.\s]+/u)
    .filter(Boolean)
    .map((part) => `${part[0]?.toUpperCase() ?? ""}${part.slice(1)}`)
    .join(" ");
}

function kindLabel(kind: MemoryKind): string {
  return kind === "context_note" ? "Context note" : titleCase(kind);
}

function itemHeading(item: Record<string, unknown>): string {
  return (
    text(item.headline) ??
    text(item.claim) ??
    text(item.condition_summary) ??
    text(item.scope_label) ??
    text(item.narrative) ??
    "Memory item"
  );
}

function itemSummary(item: Record<string, unknown>): string | undefined {
  const heading = itemHeading(item);
  const candidate =
    text(item.summary) ??
    text(item.narrative) ??
    text(item.outlook) ??
    text(item.callback_condition);
  return candidate === heading ? undefined : candidate;
}

function labeledEntities(item: Record<string, unknown>): string[] {
  return ["subjects", "participants", "assets"].flatMap((field) =>
    records(item[field]).flatMap((entity) => {
      const label = text(entity.label);
      const qualifier = text(entity.role) ?? text(entity.direction);
      return label ? [`${label}${qualifier ? ` · ${qualifier}` : ""}`] : [];
    }),
  );
}

function MemoryItemCard({
  item,
  source,
}: {
  item: Record<string, unknown>;
  source?: string;
}): React.JSX.Element {
  const kind = memoryKind(item.kind);
  const status = text(item.status);
  const relevantWeek = numberValue(item.relevant_week);
  const dueWeek = numberValue(item.due_week);
  const entities = labeledEntities(item);
  return (
    <article className="rounded-md border border-border bg-background p-4">
      <div className="flex flex-wrap items-center gap-2">
        {kind ? <Badge variant="outline">{kindLabel(kind)}</Badge> : null}
        {status ? <Badge variant="secondary">{titleCase(status)}</Badge> : null}
        {source ? (
          <span className="text-xs text-muted-foreground">{source}</span>
        ) : null}
      </div>
      <h5 className="mt-3 font-semibold leading-6">{itemHeading(item)}</h5>
      {itemSummary(item) ? (
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {itemSummary(item)}
        </p>
      ) : null}
      {entities.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
          {entities.map((entity) => (
            <span key={entity} className="rounded-full bg-muted px-2.5 py-1">
              {entity}
            </span>
          ))}
        </div>
      ) : null}
      {relevantWeek !== undefined || dueWeek !== undefined ? (
        <p className="mt-3 text-xs text-muted-foreground">
          {dueWeek !== undefined
            ? `Due week ${String(dueWeek)}`
            : `Relevant week ${String(relevantWeek)}`}
        </p>
      ) : null}
    </article>
  );
}

function MemoryGroup({
  title,
  description,
  items,
}: {
  title: string;
  description: string;
  items: Record<string, unknown>[];
}): React.JSX.Element {
  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h4 className="font-semibold">{title}</h4>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {description}
          </p>
        </div>
        <Badge variant="outline">{items.length}</Badge>
      </div>
      {items.length > 0 ? (
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {items.map((item, index) => (
            <MemoryItemCard
              key={`${text(item.kind) ?? "memory"}-${String(index)}`}
              item={item}
            />
          ))}
        </div>
      ) : (
        <p className="mt-4 rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
          None retrieved.
        </p>
      )}
    </section>
  );
}

function RecallStatusBadge({
  status,
}: {
  status: GenerationMemoryRecall["status"];
}): React.JSX.Element {
  if (status === "failed") return <Badge variant="destructive">Failed</Badge>;
  if (status === "partial") return <Badge variant="secondary">Partial</Badge>;
  return <Badge variant="outline">Complete</Badge>;
}

function AutomaticRecallSection({
  recall,
  enabled,
  pending,
  generationActive,
}: {
  recall: GenerationMemoryRecall | null | undefined;
  enabled: boolean;
  pending: boolean;
  generationActive: boolean;
}): React.JSX.Element {
  if (!enabled) {
    return (
      <section className="rounded-lg border border-border bg-card p-5">
        <div className="flex items-center gap-2">
          <BrainCircuit
            className="size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <h3 className="font-semibold">Automatic recall</h3>
          <Badge variant="outline">Disabled</Badge>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          This generation kept memory search and closeout available but did not
          inject a generation-start recall prelude.
        </p>
      </section>
    );
  }
  if (pending || recall == null) {
    return (
      <section className="rounded-lg border border-border bg-card p-5">
        <div className="flex items-center gap-2">
          <BrainCircuit
            className="size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <h3 className="font-semibold">Automatic recall</h3>
          <Badge variant={generationActive ? "secondary" : "outline"}>
            {generationActive ? "Pending" : "Not recorded"}
          </Badge>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          {generationActive
            ? "Generation-start memory context is being prepared."
            : "No automatic recall resource was recorded for this generation."}
        </p>
      </section>
    );
  }

  const result = record(recall.result) ?? {};
  const callbacks = records(result.due_callbacks);
  const standing = records(result.standing_context);
  const likely = records(result.likely_relevant_memories);
  return (
    <section aria-labelledby="automatic-recall-heading">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <BrainCircuit
              className="size-5 text-muted-foreground"
              aria-hidden="true"
            />
            <h3
              id="automatic-recall-heading"
              className="font-editorial text-2xl font-semibold"
            >
              Automatic recall
            </h3>
            <RecallStatusBadge status={recall.status} />
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            The exact semantic memory supplied before the assignment, organized
            by why it was retrieved.
          </p>
        </div>
        <span className="text-xs text-muted-foreground">
          <DateTime value={recall.created_at} />
        </span>
      </div>
      <div className="space-y-4">
        <MemoryGroup
          title="Due callbacks"
          description="Trigger conditions due for this season, week, and knowledge cutoff."
          items={callbacks}
        />
        <MemoryGroup
          title="Standing context"
          description="Applicable league, season, and focused-team context notes."
          items={standing}
        />
        <MemoryGroup
          title="Likely relevant"
          description="Bounded facts, events, and storylines selected from assignment intent."
          items={likely}
        />
      </div>
      <details className="mt-4 rounded-lg border border-border bg-card p-5">
        <summary className="cursor-pointer text-sm font-semibold">
          Technical recall record
        </summary>
        <p className="mt-2 text-xs leading-5 text-muted-foreground">
          Exact model context and application-only retrieval metadata for audit
          and debugging.
        </p>
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <StructuredContentViewer
            title="Exact context text"
            content={recall.result_text}
          />
          <StructuredContentViewer title="Metadata" content={recall.metadata} />
        </div>
      </details>
    </section>
  );
}

function searchedMemories(toolCalls: ToolCall[]): {
  key: string;
  query: string;
  items: Record<string, unknown>[];
}[] {
  return toolCalls.flatMap((call) => {
    if (call.tool_name !== "search_memory") return [];
    const result = record(call.result);
    const argumentsValue = record(call.arguments) ?? {};
    const query = text(argumentsValue.text) ?? "Editorial memory search";
    return [
      {
        key: call.id,
        query,
        items: records(result?.memories),
      },
    ];
  });
}

function savedMemories(toolCalls: ToolCall[]): SavedMemory[] {
  return toolCalls.flatMap((call) => {
    const defaultKind = writeKinds[call.tool_name];
    if (!defaultKind) return [];
    const result = record(call.result);
    if (!result) return [];
    const activity = record(record(call.metadata)?.memory_activity);
    const activityItems = records(activity?.items);
    const argumentsValue = record(call.arguments) ?? {};
    const triggerSpecs = records(argumentsValue.trigger_specs);
    const described = activityItems.flatMap((item, index) => {
      const kind = memoryKind(item.kind);
      if (!kind) return [];
      const operation: SavedMemory["operation"] =
        item.operation === "create" || item.operation === "replace"
          ? item.operation
          : "unknown";
      const path = text(item.path) ?? "result";
      const triggerMatch = /^arguments\.trigger_specs\.(\d+)$/.exec(path);
      const savedArguments = triggerMatch
        ? (triggerSpecs[Number(triggerMatch[1])] ?? item)
        : argumentsValue;
      return [
        {
          key: `${call.id}-${String(index)}`,
          kind,
          operation,
          arguments: savedArguments,
        },
      ];
    });
    if (described.length > 0) return described;

    return result.saved === true
      ? [
          {
            key: call.id,
            kind: defaultKind,
            operation: "unknown",
            arguments: argumentsValue,
          },
        ]
      : [];
  });
}

function savedHeading(memory: SavedMemory): string {
  const value = memory.arguments;
  return (
    text(value.headline) ??
    text(value.narrative) ??
    text(value.value) ??
    text(value.id) ??
    text(value.key) ??
    text(value.roster_key) ??
    `Saved ${kindLabel(memory.kind).toLowerCase()}`
  );
}

function savedSummary(memory: SavedMemory): string | undefined {
  const value = memory.arguments;
  return (
    text(value.summary) ??
    text(value.outlook) ??
    text(value.condition_summary) ??
    text(record(value.condition)?.summary)
  );
}

function SavedMemoryCard({
  memory,
}: {
  memory: SavedMemory;
}): React.JSX.Element {
  const operationLabel =
    memory.operation === "create"
      ? "New"
      : memory.operation === "replace"
        ? "Updated"
        : "Saved";
  return (
    <article className="rounded-md border border-border bg-background p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{kindLabel(memory.kind)}</Badge>
        <Badge
          variant={memory.operation === "create" ? "default" : "secondary"}
        >
          {operationLabel}
        </Badge>
      </div>
      <h5 className="mt-3 font-semibold leading-6">{savedHeading(memory)}</h5>
      {savedSummary(memory) ? (
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {savedSummary(memory)}
        </p>
      ) : null}
    </article>
  );
}

function InlineError({
  title,
  error,
  onRetry,
}: {
  title: string;
  error: unknown;
  onRetry: () => void;
}): React.JSX.Element {
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-5">
      <CircleAlert className="size-5 text-destructive" aria-hidden="true" />
      <h4 className="mt-3 font-semibold">{title}</h4>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        {error instanceof ApiError
          ? error.message
          : "This durable memory resource could not be loaded."}
      </p>
      <Button className="mt-3" variant="outline" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

export function GenerationMemoryPanel({
  competitionId,
  generationId,
  active,
  generationActive,
  automaticRecallEnabled,
}: GenerationMemoryPanelProps): React.JSX.Element | null {
  const recallQuery = useGenerationMemoryRecall(
    competitionId,
    generationId,
    active && automaticRecallEnabled,
    generationActive,
  );
  const activityQuery = useGenerationMemoryToolCalls(
    competitionId,
    generationId,
    active,
    generationActive,
  );

  if (!active) return null;
  const searches = searchedMemories(activityQuery.data ?? []);
  const saves = savedMemories(activityQuery.data ?? []);
  const savesByKind = new Map<MemoryKind, SavedMemory[]>();
  for (const memory of saves) {
    savesByKind.set(memory.kind, [
      ...(savesByKind.get(memory.kind) ?? []),
      memory,
    ]);
  }

  return (
    <div className="min-w-0 space-y-8">
      {recallQuery.isError && automaticRecallEnabled ? (
        <InlineError
          title="Automatic recall unavailable"
          error={recallQuery.error}
          onRetry={() => void recallQuery.refetch()}
        />
      ) : (
        <AutomaticRecallSection
          recall={recallQuery.data?.recall}
          enabled={automaticRecallEnabled}
          pending={recallQuery.isPending}
          generationActive={generationActive}
        />
      )}

      <section aria-labelledby="supplemental-memory-heading">
        <div className="flex items-center gap-2">
          <Search className="size-5 text-muted-foreground" aria-hidden="true" />
          <h3
            id="supplemental-memory-heading"
            className="font-editorial text-2xl font-semibold"
          >
            Supplemental searches
          </h3>
          <Badge variant="outline">{searches.length}</Badge>
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
          Additional memory explicitly requested during research. These items
          were presented to the reporter; presentation alone does not prove they
          appeared in the article.
        </p>
        {activityQuery.isPending ? (
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
        ) : activityQuery.isError ? (
          <div className="mt-4">
            <InlineError
              title="Memory activity unavailable"
              error={activityQuery.error}
              onRetry={() => void activityQuery.refetch()}
            />
          </div>
        ) : searches.length > 0 ? (
          <div className="mt-4 space-y-4">
            {searches.map((search) => (
              <section
                key={search.key}
                className="rounded-lg border border-border bg-card p-5"
              >
                <h4 className="font-semibold">{search.query}</h4>
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  {search.items.map((item, index) => (
                    <MemoryItemCard
                      key={`${search.key}-${String(index)}`}
                      item={item}
                      source="Supplemental search"
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : (
          <p className="mt-4 rounded-md border border-dashed border-border bg-card/60 p-5 text-sm text-muted-foreground">
            No supplemental memory searches were recorded.
          </p>
        )}
      </section>

      <section aria-labelledby="saved-memory-heading">
        <div className="flex items-center gap-2">
          <Save className="size-5 text-muted-foreground" aria-hidden="true" />
          <h3
            id="saved-memory-heading"
            className="font-editorial text-2xl font-semibold"
          >
            Memories saved
          </h3>
          <Badge variant="outline">{saves.length}</Badge>
          {generationActive && activityQuery.isFetching ? (
            <LoaderCircle
              className="size-4 animate-spin text-muted-foreground"
              aria-label="Updating memory activity"
            />
          ) : null}
        </div>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
          Successful reporter-selected memory proposals, grouped by semantic
          type and labeled as new canonical items or updates.
        </p>
        {saves.length > 0 ? (
          <div className="mt-4 space-y-4">
            {memoryKinds.flatMap((kind) => {
              const items = savesByKind.get(kind) ?? [];
              if (items.length === 0) return [];
              return [
                <section
                  key={kind}
                  className="rounded-lg border border-border bg-card p-5"
                >
                  <div className="flex items-center justify-between gap-3">
                    <h4 className="font-semibold">{kindLabel(kind)}</h4>
                    <Badge variant="outline">{items.length}</Badge>
                  </div>
                  <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    {items.map((memory) => (
                      <SavedMemoryCard key={memory.key} memory={memory} />
                    ))}
                  </div>
                </section>,
              ];
            })}
          </div>
        ) : !activityQuery.isPending && !activityQuery.isError ? (
          <p className="mt-4 rounded-md border border-dashed border-border bg-card/60 p-5 text-sm text-muted-foreground">
            No memory creates or updates were recorded for this generation.
          </p>
        ) : null}
      </section>
    </div>
  );
}
