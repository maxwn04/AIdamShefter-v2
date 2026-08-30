import {
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Cpu,
  LoaderCircle,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { ApiError } from "@/api/errors";
import { DateTime } from "@/components/shared/date-time";
import { StructuredContentViewer } from "@/components/shared/structured-content-viewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  AICallStatus,
  AICallSummary,
  GenerationMemoryRecall,
  ToolCallStatus,
  ToolCallSummary,
} from "@/features/execution/api";
import {
  useAICallDetail,
  useAICallList,
  useGenerationToolCallList,
  useGenerationMemoryRecall,
  useToolCallDetail,
} from "@/features/execution/queries";
import { cn } from "@/lib/utils";

const EXECUTION_PAGE_SIZE = 50;

interface ExecutionTimelineProps {
  competitionId: string;
  generationId: string;
  active: boolean;
  generationActive: boolean;
}

type BadgeVariant = "outline" | "secondary" | "destructive";

type ExecutionSelection =
  { kind: "ai"; id: string } | { kind: "tool"; id: string };

interface TurnGroup {
  attempts: AICallSummary[];
  turnNumber: number;
}

function positivePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

function formatDuration(milliseconds: number | null): string {
  if (milliseconds === null) return "In progress";
  if (milliseconds < 1_000) return `${String(milliseconds)} ms`;
  return `${(milliseconds / 1_000).toFixed(milliseconds < 10_000 ? 1 : 0)} s`;
}

function formatTokenCount(value: number | null | undefined): string {
  if (value == null) return "Tokens unknown";
  return `${new Intl.NumberFormat().format(value)} tokens`;
}

function modelLabel(provider: string | null, model: string): string {
  return provider ? `${provider}/${model}` : model;
}

function aiStatus(status: AICallStatus): {
  label: string;
  variant: BadgeVariant;
} {
  if (status === "succeeded") return { label: "Succeeded", variant: "outline" };
  if (status === "retryable_error")
    return { label: "Retryable error", variant: "destructive" };
  if (status === "fatal_error")
    return { label: "Fatal error", variant: "destructive" };
  if (status === "cancelled") return { label: "Cancelled", variant: "outline" };
  if (status === "started") return { label: "Running", variant: "secondary" };
  return { label: "Unknown outcome", variant: "secondary" };
}

function toolStatus(status: ToolCallStatus): {
  label: string;
  variant: BadgeVariant;
} {
  if (status === "succeeded") return { label: "Succeeded", variant: "outline" };
  if (status === "failed") return { label: "Failed", variant: "destructive" };
  if (status === "cancelled") return { label: "Cancelled", variant: "outline" };
  return { label: "Running", variant: "secondary" };
}

function recallStatus(status: GenerationMemoryRecall["status"]): {
  label: string;
  variant: BadgeVariant;
} {
  if (status === "complete") return { label: "Complete", variant: "outline" };
  if (status === "partial") return { label: "Partial", variant: "secondary" };
  return { label: "Failed", variant: "destructive" };
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
          : "This durable execution resource could not be loaded."}
      </p>
      <Button className="mt-3" variant="outline" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

function AutomaticRecallCard({
  competitionId,
  generationId,
  active,
  generationActive,
}: ExecutionTimelineProps): React.JSX.Element | null {
  const query = useGenerationMemoryRecall(
    competitionId,
    generationId,
    active,
    generationActive,
  );

  if (!active) return null;
  if (query.isError) {
    return (
      <div className="mb-5">
        <InlineError
          title="Automatic recall unavailable"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      </div>
    );
  }
  if (query.isPending || query.data.recall === null) {
    return (
      <article className="mb-5 rounded-lg border border-border bg-card p-4">
        <div className="flex items-center gap-2">
          <BrainCircuit
            className="size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <h3 className="font-semibold">Automatic recall</h3>
          {query.isPending || generationActive ? (
            <Badge variant="secondary">Pending</Badge>
          ) : (
            <Badge variant="outline">Not recorded</Badge>
          )}
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          {generationActive
            ? "Generation-start memory context is being prepared."
            : "This generation has no automatic recall resource."}
        </p>
      </article>
    );
  }

  const recall = query.data.recall;
  const presentation = recallStatus(recall.status);
  return (
    <article className="mb-5 overflow-hidden rounded-lg border border-border bg-card">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-muted/30 px-4 py-3">
        <div className="flex items-center gap-2">
          <BrainCircuit
            className="size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <h3 className="font-semibold">Automatic recall</h3>
          <Badge variant={presentation.variant}>{presentation.label}</Badge>
        </div>
        <span className="text-xs text-muted-foreground">
          <DateTime value={recall.created_at} />
        </span>
      </header>
      <div className="grid min-w-0 gap-3 p-4 xl:grid-cols-2">
        <StructuredContentViewer
          title="Result"
          content={recall.result}
          defaultOpen
        />
        <StructuredContentViewer
          title="Exact context text"
          content={recall.result_text}
          defaultOpen
        />
        <StructuredContentViewer
          title="Metadata"
          content={recall.metadata}
          defaultOpen
        />
      </div>
    </article>
  );
}

function Pager({
  label,
  page,
  totalPages,
  total,
  onPageChange,
}: {
  label: string;
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
}): React.JSX.Element | null {
  if (totalPages <= 1) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 text-xs">
      <span className="text-muted-foreground">
        {label} page {page} of {totalPages} · {total} total
      </span>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          aria-label={`Previous ${label.toLowerCase()} page`}
          onClick={() => {
            onPageChange(page - 1);
          }}
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= totalPages}
          aria-label={`Next ${label.toLowerCase()} page`}
          onClick={() => {
            onPageChange(page + 1);
          }}
        >
          Next
          <ArrowRight className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

function AICallDetail({
  competitionId,
  generationId,
  summary,
}: {
  competitionId: string;
  generationId: string;
  summary: AICallSummary;
}): React.JSX.Element {
  const query = useAICallDetail(
    competitionId,
    generationId,
    summary.id,
    true,
    summary.status === "started",
  );

  return (
    <div className="border-t border-primary/15 bg-muted/20 p-3 sm:p-4">
      {query.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : query.isError ? (
        <InlineError
          title="AI-call detail unavailable"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      ) : (
        <div className="grid min-w-0 gap-3 xl:grid-cols-2">
          <StructuredContentViewer
            title="Request parameters"
            content={query.data.ai_call.request_parameters}
            defaultOpen
          />
          <StructuredContentViewer
            title="Input messages"
            content={query.data.ai_call.input_messages}
            defaultOpen
          />
          <StructuredContentViewer
            title="Tool definitions"
            content={query.data.ai_call.tool_definitions}
            defaultOpen
          />
          <StructuredContentViewer
            title="Provider response"
            content={query.data.ai_call.provider_response ?? undefined}
            defaultOpen
          />
          <StructuredContentViewer
            title="Error"
            content={query.data.ai_call.error ?? undefined}
            defaultOpen
          />
        </div>
      )}
    </div>
  );
}

function ToolCallDetail({
  competitionId,
  generationId,
  summary,
}: {
  competitionId: string;
  generationId: string;
  summary: ToolCallSummary;
}): React.JSX.Element {
  const query = useToolCallDetail(
    competitionId,
    generationId,
    summary.ai_call_id,
    summary.id,
    true,
    summary.status === "running",
  );

  return (
    <div className="border-t border-primary/15 bg-primary/[0.025] p-3 sm:p-4">
      {query.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      ) : query.isError ? (
        <InlineError
          title="Tool-call detail unavailable"
          error={query.error}
          onRetry={() => void query.refetch()}
        />
      ) : (
        <div className="grid min-w-0 gap-3 xl:grid-cols-2">
          <StructuredContentViewer
            title="Arguments"
            content={query.data.tool_call.arguments}
            defaultOpen
          />
          <StructuredContentViewer
            title="Result"
            content={query.data.tool_call.result ?? undefined}
            defaultOpen
          />
          <StructuredContentViewer
            title="Exact result text"
            content={query.data.tool_call.result_text ?? undefined}
            defaultOpen
          />
          <StructuredContentViewer
            title="Metadata"
            content={query.data.tool_call.metadata}
            defaultOpen
          />
          <StructuredContentViewer
            title="Error"
            content={
              query.data.tool_call.error ??
              query.data.tool_call.error_text ??
              undefined
            }
            defaultOpen
          />
        </div>
      )}
    </div>
  );
}

function ToolCallRow({
  competitionId,
  generationId,
  summary,
  selected,
  onSelect,
}: {
  competitionId: string;
  generationId: string;
  summary: ToolCallSummary;
  selected: boolean;
  onSelect: () => void;
}): React.JSX.Element {
  const presentation = toolStatus(summary.status);
  const regionId = `tool-call-${summary.id}`;

  return (
    <li className="border-t border-border/70 first:border-t-0">
      <button
        type="button"
        className={cn(
          "flex w-full items-start gap-2 px-3 py-2.5 text-left outline-none transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:pl-11",
          selected && "bg-primary/5",
        )}
        aria-expanded={selected}
        aria-controls={regionId}
        onClick={onSelect}
      >
        {selected ? (
          <ChevronDown
            className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
        ) : (
          <ChevronRight
            className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
        )}
        <Wrench
          className="mt-0.5 size-3.5 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="break-all font-mono text-xs font-medium">
              {summary.tool_name}
            </span>
            <Badge variant={presentation.variant}>{presentation.label}</Badge>
          </span>
          <span className="mt-1 block text-[0.7rem] leading-4 text-muted-foreground">
            Tool {summary.tool_ordinal + 1} ·{" "}
            {formatDuration(summary.duration_ms)} ·{" "}
            {summary.implementation_version}
          </span>
        </span>
      </button>
      {selected ? (
        <div id={regionId}>
          <ToolCallDetail
            competitionId={competitionId}
            generationId={generationId}
            summary={summary}
          />
        </div>
      ) : null}
    </li>
  );
}

function AICallRow({
  competitionId,
  generationId,
  summary,
  tools,
  selection,
  onSelect,
}: {
  competitionId: string;
  generationId: string;
  summary: AICallSummary;
  tools: ToolCallSummary[];
  selection: ExecutionSelection | null;
  onSelect: (selection: ExecutionSelection) => void;
}): React.JSX.Element {
  const selected = selection?.kind === "ai" && selection.id === summary.id;
  const presentation = aiStatus(summary.status);
  const actualModel = summary.actual_model
    ? modelLabel(summary.actual_provider, summary.actual_model)
    : null;
  const regionId = `ai-call-${summary.id}`;

  return (
    <li className="border-t border-border first:border-t-0">
      <button
        type="button"
        className={cn(
          "flex w-full items-start gap-3 px-3 py-3 text-left outline-none transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:px-4",
          selected && "bg-primary/5",
        )}
        aria-expanded={selected}
        aria-controls={regionId}
        onClick={() => {
          onSelect({ kind: "ai", id: summary.id });
        }}
      >
        {selected ? (
          <ChevronDown className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        ) : (
          <ChevronRight className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        )}
        <Cpu
          className="mt-0.5 size-4 shrink-0 text-muted-foreground"
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-semibold">
              {summary.attempt_number === 0
                ? "Model call"
                : `Retry ${String(summary.attempt_number)}`}
            </span>
            <Badge variant={presentation.variant}>{presentation.label}</Badge>
            {tools.length > 0 ? (
              <span className="text-xs text-muted-foreground">
                {tools.length} {tools.length === 1 ? "tool" : "tools"}
              </span>
            ) : null}
          </span>
          <span className="mt-1.5 block break-all font-mono text-xs">
            {modelLabel(summary.requested_provider, summary.requested_model)}
            {actualModel &&
            actualModel !==
              modelLabel(summary.requested_provider, summary.requested_model)
              ? ` → ${actualModel}`
              : ""}
          </span>
          <span className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>{formatDuration(summary.latency_ms)}</span>
            <span>{formatTokenCount(summary.usage.total_tokens)}</span>
            <span>{summary.finish_reason ?? "No finish reason"}</span>
          </span>
        </span>
      </button>

      {selected ? (
        <div id={regionId}>
          <AICallDetail
            competitionId={competitionId}
            generationId={generationId}
            summary={summary}
          />
        </div>
      ) : null}

      {tools.length > 0 ? (
        <ol className="border-t border-border bg-muted/10">
          {tools.map((tool) => (
            <ToolCallRow
              key={tool.id}
              competitionId={competitionId}
              generationId={generationId}
              summary={tool}
              selected={selection?.kind === "tool" && selection.id === tool.id}
              onSelect={() => {
                onSelect({ kind: "tool", id: tool.id });
              }}
            />
          ))}
        </ol>
      ) : null}
    </li>
  );
}

function TurnCard({
  competitionId,
  generationId,
  turn,
  toolsByAICall,
  selection,
  onSelect,
}: {
  competitionId: string;
  generationId: string;
  turn: TurnGroup;
  toolsByAICall: ReadonlyMap<string, ToolCallSummary[]>;
  selection: ExecutionSelection | null;
  onSelect: (selection: ExecutionSelection) => void;
}): React.JSX.Element {
  const [expanded, setExpanded] = useState(true);
  const toolCount = turn.attempts.reduce(
    (total, attempt) => total + (toolsByAICall.get(attempt.id)?.length ?? 0),
    0,
  );
  const totalTokens = turn.attempts.reduce<number | null>((total, attempt) => {
    if (attempt.usage.total_tokens == null) return total;
    return (total ?? 0) + attempt.usage.total_tokens;
  }, null);
  const regionId = `turn-${String(turn.turnNumber)}-executions`;

  return (
    <article className="overflow-hidden rounded-lg border border-border bg-card">
      <header
        className={cn("bg-muted/30", expanded && "border-b border-border")}
      >
        <button
          type="button"
          className="flex w-full flex-wrap items-center justify-between gap-x-4 gap-y-1 px-3 py-2.5 text-left outline-none transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:px-4"
          aria-expanded={expanded}
          aria-controls={regionId}
          onClick={() => {
            setExpanded((current) => !current);
          }}
        >
          <span className="flex items-center gap-2">
            {expanded ? (
              <ChevronDown className="size-4 shrink-0" aria-hidden="true" />
            ) : (
              <ChevronRight className="size-4 shrink-0" aria-hidden="true" />
            )}
            <span className="flex items-baseline gap-3">
              <span className="font-semibold">Turn {turn.turnNumber}</span>
              <span className="text-xs text-muted-foreground">
                <DateTime value={turn.attempts[0]?.started_at ?? ""} />
              </span>
            </span>
          </span>
          <span className="text-xs text-muted-foreground">
            {turn.attempts.length}{" "}
            {turn.attempts.length === 1 ? "attempt" : "attempts"}
            {toolCount > 0 ? ` · ${String(toolCount)} tools` : ""}
            {totalTokens === null
              ? ""
              : ` · ${new Intl.NumberFormat().format(totalTokens)} tokens`}
          </span>
        </button>
      </header>
      {expanded ? (
        <ol id={regionId}>
          {turn.attempts.map((attempt) => (
            <AICallRow
              key={attempt.id}
              competitionId={competitionId}
              generationId={generationId}
              summary={attempt}
              tools={toolsByAICall.get(attempt.id) ?? []}
              selection={selection}
              onSelect={onSelect}
            />
          ))}
        </ol>
      ) : null}
    </article>
  );
}

function TimelineSkeleton(): React.JSX.Element {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((item) => (
        <Skeleton key={item} className="h-32 w-full rounded-lg" />
      ))}
    </div>
  );
}

export function ExecutionTimeline({
  competitionId,
  generationId,
  active,
  generationActive,
}: ExecutionTimelineProps): React.JSX.Element | null {
  const [searchParameters, setSearchParameters] = useSearchParams();
  const [selection, setSelection] = useState<ExecutionSelection | null>(null);
  const page = positivePage(searchParameters.get("page"));
  const aiCallsQuery = useAICallList(
    competitionId,
    generationId,
    {
      limit: EXECUTION_PAGE_SIZE,
      offset: (page - 1) * EXECUTION_PAGE_SIZE,
    },
    active,
    generationActive,
  );
  const toolCallsQuery = useGenerationToolCallList(
    competitionId,
    generationId,
    active,
    generationActive,
  );
  const totalPages = pageCount(
    aiCallsQuery.data?.page.total ?? 0,
    EXECUTION_PAGE_SIZE,
  );
  const toolsByAICall = useMemo(() => {
    const grouped = new Map<string, ToolCallSummary[]>();
    for (const tool of toolCallsQuery.data ?? []) {
      const current = grouped.get(tool.ai_call_id) ?? [];
      current.push(tool);
      grouped.set(tool.ai_call_id, current);
    }
    for (const tools of grouped.values()) {
      tools.sort((left, right) => left.tool_ordinal - right.tool_ordinal);
    }
    return grouped;
  }, [toolCallsQuery.data]);
  const turns = useMemo(() => {
    const grouped = new Map<number, AICallSummary[]>();
    for (const call of aiCallsQuery.data?.page.items ?? []) {
      const current = grouped.get(call.turn_number) ?? [];
      current.push(call);
      grouped.set(call.turn_number, current);
    }
    return [...grouped.entries()]
      .sort(([left], [right]) => left - right)
      .map(([turnNumber, attempts]) => ({
        turnNumber,
        attempts: attempts.sort(
          (left, right) => left.attempt_number - right.attempt_number,
        ),
      }));
  }, [aiCallsQuery.data]);

  useEffect(() => {
    if (!active || !aiCallsQuery.data || page <= totalPages) return;
    const next = new URLSearchParams(searchParameters);
    if (totalPages === 1) next.delete("page");
    else next.set("page", String(totalPages));
    setSearchParameters(next, { replace: true });
  }, [
    active,
    aiCallsQuery.data,
    page,
    searchParameters,
    setSearchParameters,
    totalPages,
  ]);

  if (!active) return null;
  if (aiCallsQuery.isPending)
    return (
      <>
        <AutomaticRecallCard
          {...{ competitionId, generationId, active, generationActive }}
        />
        <TimelineSkeleton />
      </>
    );
  if (aiCallsQuery.isError) {
    return (
      <>
        <AutomaticRecallCard
          {...{ competitionId, generationId, active, generationActive }}
        />
        <InlineError
          title="Execution history unavailable"
          error={aiCallsQuery.error}
          onRetry={() => void aiCallsQuery.refetch()}
        />
      </>
    );
  }
  if (aiCallsQuery.data.page.items.length === 0 && page === 1) {
    return (
      <>
        <AutomaticRecallCard
          {...{ competitionId, generationId, active, generationActive }}
        />
        <div className="rounded-lg border border-dashed border-border bg-card/60 p-8 text-center sm:p-12">
          <Cpu
            className="mx-auto size-8 text-muted-foreground"
            aria-hidden="true"
          />
          <h3 className="mt-5 font-editorial text-2xl font-semibold">
            No AI attempts recorded
          </h3>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
            This generation has not recorded a model attempt yet.
          </p>
        </div>
      </>
    );
  }

  function setPage(nextPage: number): void {
    const next = new URLSearchParams(searchParameters);
    if (nextPage === 1) next.delete("page");
    else next.set("page", String(nextPage));
    setSelection(null);
    setSearchParameters(next);
  }

  function select(nextSelection: ExecutionSelection): void {
    setSelection((current) =>
      current?.kind === nextSelection.kind && current.id === nextSelection.id
        ? null
        : nextSelection,
    );
  }

  const toolCount = toolCallsQuery.data?.length ?? 0;
  const updating = aiCallsQuery.isFetching || toolCallsQuery.isFetching;

  return (
    <section aria-labelledby="execution-timeline-heading" className="min-w-0">
      <AutomaticRecallCard
        {...{ competitionId, generationId, active, generationActive }}
      />
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3
            id="execution-timeline-heading"
            className="font-editorial text-2xl font-semibold"
          >
            Turn stream
          </h3>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Model and tool activity stays visible in run order. Select one row
            to inspect all of its exact payloads.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {updating ? (
            <>
              <LoaderCircle
                className="size-3 animate-spin"
                aria-hidden="true"
              />
              <span role="status">Updating activity…</span>
            </>
          ) : (
            <span>
              {aiCallsQuery.data.page.total} attempts · {toolCount} tools
            </span>
          )}
        </div>
      </div>

      {toolCallsQuery.isError ? (
        <div
          className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm"
          role="alert"
        >
          <span>
            Tool activity could not be loaded; model attempts remain available.
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void toolCallsQuery.refetch()}
          >
            Try again
          </Button>
        </div>
      ) : null}

      <ol className="space-y-3">
        {turns.map((turn) => (
          <li key={turn.turnNumber}>
            <TurnCard
              competitionId={competitionId}
              generationId={generationId}
              turn={turn}
              toolsByAICall={toolsByAICall}
              selection={selection}
              onSelect={select}
            />
          </li>
        ))}
      </ol>
      <div className="mt-5">
        <Pager
          label="AI attempts"
          page={page}
          totalPages={totalPages}
          total={aiCallsQuery.data.page.total}
          onPageChange={setPage}
        />
      </div>
    </section>
  );
}
