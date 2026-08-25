import {
  ArrowLeft,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Cpu,
  LoaderCircle,
  Wrench,
} from "lucide-react";
import { useEffect, useState } from "react";
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
  TokenUsage,
  ToolCallStatus,
  ToolCallSummary,
} from "@/features/execution/api";
import {
  useAICallDetail,
  useAICallList,
  useToolCallDetail,
  useToolCallList,
} from "@/features/execution/queries";

const EXECUTION_PAGE_SIZE = 25;
const TOOL_PAGE_SIZE = 25;

interface ExecutionTimelineProps {
  competitionId: string;
  generationId: string;
  active: boolean;
  generationActive: boolean;
}

type BadgeVariant = "outline" | "secondary" | "destructive";

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

function TokenSummary({ usage }: { usage: TokenUsage }): React.JSX.Element {
  const values = [
    ["Total", usage.total_tokens],
    ["Input", usage.input_tokens],
    ["Cached", usage.cached_input_tokens],
    ["Output", usage.output_tokens],
    ["Reasoning", usage.reasoning_tokens],
  ] as const;
  return (
    <dl className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {values.map(([label, value]) => (
        <div key={label} className="flex gap-1">
          <dt>{label}</dt>
          <dd className="font-medium tabular-nums text-foreground">
            {value ?? "—"}
          </dd>
        </div>
      ))}
    </dl>
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
          : "This durable execution resource could not be loaded."}
      </p>
      <Button className="mt-3" variant="outline" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
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

function ToolCallRow({
  competitionId,
  generationId,
  aiCallId,
  summary,
}: {
  competitionId: string;
  generationId: string;
  aiCallId: string;
  summary: ToolCallSummary;
}): React.JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const detailQuery = useToolCallDetail(
    competitionId,
    generationId,
    aiCallId,
    summary.id,
    expanded,
  );
  const presentation = toolStatus(summary.status);
  const regionId = `tool-call-${summary.id}`;

  return (
    <li className="rounded-lg border border-border bg-background">
      <button
        type="button"
        className="flex w-full items-start gap-3 p-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
        aria-expanded={expanded}
        aria-controls={regionId}
        onClick={() => {
          setExpanded((value) => !value);
        }}
      >
        {expanded ? (
          <ChevronDown className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        ) : (
          <ChevronRight className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        )}
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="break-all font-mono text-sm font-medium">
              {summary.tool_name}
            </span>
            <Badge variant={presentation.variant}>{presentation.label}</Badge>
          </span>
          <span className="mt-2 block text-xs text-muted-foreground">
            Tool {summary.tool_ordinal} · {formatDuration(summary.duration_ms)}{" "}
            · {summary.implementation_version}
          </span>
        </span>
      </button>

      {expanded ? (
        <div id={regionId} className="border-t border-border p-4">
          {detailQuery.isPending ? (
            <div className="space-y-2">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : detailQuery.isError ? (
            <InlineError
              title="Tool-call detail unavailable"
              error={detailQuery.error}
              onRetry={() => void detailQuery.refetch()}
            />
          ) : (
            <div className="grid min-w-0 gap-3 xl:grid-cols-2">
              <StructuredContentViewer
                title="Arguments"
                content={detailQuery.data.tool_call.arguments}
              />
              <StructuredContentViewer
                title="Structured result"
                content={
                  detailQuery.data.tool_call.structured_result ?? undefined
                }
              />
              <StructuredContentViewer
                title="Full result text"
                content={
                  detailQuery.data.tool_call.full_result_text ?? undefined
                }
              />
              <StructuredContentViewer
                title="Error"
                content={
                  detailQuery.data.tool_call.error ??
                  detailQuery.data.tool_call.error_text ??
                  undefined
                }
              />
            </div>
          )}
        </div>
      ) : null}
    </li>
  );
}

function ToolCallsPanel({
  competitionId,
  generationId,
  aiCallId,
}: {
  competitionId: string;
  generationId: string;
  aiCallId: string;
}): React.JSX.Element {
  const [page, setPage] = useState(1);
  const query = useToolCallList(
    competitionId,
    generationId,
    aiCallId,
    {
      limit: TOOL_PAGE_SIZE,
      offset: (page - 1) * TOOL_PAGE_SIZE,
    },
    true,
  );
  const totalPages = pageCount(query.data?.page.total ?? 0, TOOL_PAGE_SIZE);

  return (
    <section
      className="mt-5 border-t border-border pt-5"
      aria-labelledby={`tools-${aiCallId}`}
    >
      <div className="flex items-center justify-between gap-3">
        <h4
          id={`tools-${aiCallId}`}
          className="flex items-center gap-2 font-semibold"
        >
          <Wrench className="size-4 text-muted-foreground" aria-hidden="true" />
          Tool calls
        </h4>
        {query.isFetching && !query.isPending ? (
          <span className="text-xs text-muted-foreground" role="status">
            Updating…
          </span>
        ) : null}
      </div>

      {query.isPending ? (
        <div className="mt-3 space-y-2">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : query.isError ? (
        <div className="mt-3">
          <InlineError
            title="Tool-call history unavailable"
            error={query.error}
            onRetry={() => void query.refetch()}
          />
        </div>
      ) : query.data.page.items.length === 0 ? (
        <p className="mt-3 rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
          This AI attempt recorded no tool calls.
        </p>
      ) : (
        <>
          <ol className="mt-3 space-y-2">
            {query.data.page.items.map((toolCall) => (
              <ToolCallRow
                key={toolCall.id}
                competitionId={competitionId}
                generationId={generationId}
                aiCallId={aiCallId}
                summary={toolCall}
              />
            ))}
          </ol>
          <div className="mt-4">
            <Pager
              label="Tool calls"
              page={page}
              totalPages={totalPages}
              total={query.data.page.total}
              onPageChange={setPage}
            />
          </div>
        </>
      )}
    </section>
  );
}

function AICallBody({
  competitionId,
  generationId,
  summary,
}: {
  competitionId: string;
  generationId: string;
  summary: AICallSummary;
}): React.JSX.Element {
  const detailQuery = useAICallDetail(
    competitionId,
    generationId,
    summary.id,
    true,
  );
  return (
    <div className="border-t border-border bg-muted/20 p-4 sm:p-5">
      {detailQuery.isPending ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : detailQuery.isError ? (
        <InlineError
          title="AI-call detail unavailable"
          error={detailQuery.error}
          onRetry={() => void detailQuery.refetch()}
        />
      ) : (
        <div className="grid min-w-0 gap-3 xl:grid-cols-2">
          <StructuredContentViewer
            title="Request parameters"
            content={detailQuery.data.ai_call.request_parameters}
          />
          <StructuredContentViewer
            title="Input messages"
            content={detailQuery.data.ai_call.input_messages}
          />
          <StructuredContentViewer
            title="Tool definitions"
            content={detailQuery.data.ai_call.tool_definitions}
          />
          <StructuredContentViewer
            title="Provider response"
            content={detailQuery.data.ai_call.provider_response ?? undefined}
          />
          <StructuredContentViewer
            title="Error"
            content={detailQuery.data.ai_call.error ?? undefined}
          />
        </div>
      )}
      <ToolCallsPanel
        competitionId={competitionId}
        generationId={generationId}
        aiCallId={summary.id}
      />
    </div>
  );
}

function AICallRow({
  competitionId,
  generationId,
  summary,
}: {
  competitionId: string;
  generationId: string;
  summary: AICallSummary;
}): React.JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const presentation = aiStatus(summary.status);
  const actualModel = summary.actual_model
    ? modelLabel(summary.actual_provider, summary.actual_model)
    : "Not resolved";
  const regionId = `ai-call-${summary.id}`;

  return (
    <li className="overflow-hidden rounded-lg border border-border bg-card">
      <button
        type="button"
        className="w-full p-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:p-5"
        aria-expanded={expanded}
        aria-controls={regionId}
        onClick={() => {
          setExpanded((value) => !value);
        }}
      >
        <span className="flex items-start gap-3">
          {expanded ? (
            <ChevronDown
              className="mt-0.5 size-5 shrink-0"
              aria-hidden="true"
            />
          ) : (
            <ChevronRight
              className="mt-0.5 size-5 shrink-0"
              aria-hidden="true"
            />
          )}
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-semibold">
                Turn {summary.turn_number} · Attempt{" "}
                {summary.attempt_number + 1}
              </span>
              <Badge variant={presentation.variant}>{presentation.label}</Badge>
            </span>
            <span className="mt-3 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
              <span className="min-w-0">
                <span className="block text-muted-foreground">Model</span>
                <span className="mt-1 block break-all font-mono">
                  {modelLabel(
                    summary.requested_provider,
                    summary.requested_model,
                  )}{" "}
                  → {actualModel}
                </span>
              </span>
              <span>
                <span className="block text-muted-foreground">Timing</span>
                <span className="mt-1 block">
                  <DateTime value={summary.started_at} /> ·{" "}
                  {formatDuration(summary.latency_ms)}
                </span>
              </span>
              <span>
                <span className="block text-muted-foreground">
                  Finish reason
                </span>
                <span className="mt-1 block">
                  {summary.finish_reason ?? "—"}
                </span>
              </span>
            </span>
            <span className="mt-3 block">
              <TokenSummary usage={summary.usage} />
            </span>
          </span>
        </span>
      </button>
      {expanded ? (
        <div id={regionId}>
          <AICallBody
            competitionId={competitionId}
            generationId={generationId}
            summary={summary}
          />
        </div>
      ) : null}
    </li>
  );
}

function TimelineSkeleton(): React.JSX.Element {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((item) => (
        <Skeleton key={item} className="h-36 w-full rounded-lg" />
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
  const page = positivePage(searchParameters.get("page"));
  const query = useAICallList(
    competitionId,
    generationId,
    {
      limit: EXECUTION_PAGE_SIZE,
      offset: (page - 1) * EXECUTION_PAGE_SIZE,
    },
    active,
    generationActive,
  );
  const totalPages = pageCount(
    query.data?.page.total ?? 0,
    EXECUTION_PAGE_SIZE,
  );

  useEffect(() => {
    if (!active || !query.data || page <= totalPages) return;
    const next = new URLSearchParams(searchParameters);
    if (totalPages === 1) next.delete("page");
    else next.set("page", String(totalPages));
    setSearchParameters(next, { replace: true });
  }, [
    active,
    page,
    query.data,
    searchParameters,
    setSearchParameters,
    totalPages,
  ]);

  if (!active) return null;
  if (query.isPending) return <TimelineSkeleton />;
  if (query.isError) {
    return (
      <InlineError
        title="Execution history unavailable"
        error={query.error}
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.data.page.items.length === 0 && page === 1) {
    return (
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
    );
  }

  function setPage(nextPage: number): void {
    const next = new URLSearchParams(searchParameters);
    if (nextPage === 1) next.delete("page");
    else next.set("page", String(nextPage));
    setSearchParameters(next);
  }

  return (
    <section aria-labelledby="execution-timeline-heading" className="min-w-0">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3
            id="execution-timeline-heading"
            className="font-editorial text-2xl font-semibold"
          >
            Model attempts
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Durable turn and retry order, with tool activity nested under each
            attempt.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {query.isFetching ? (
            <>
              <LoaderCircle
                className="size-3 animate-spin"
                aria-hidden="true"
              />
              <span role="status">Updating summaries…</span>
            </>
          ) : (
            <span>
              {query.data.page.total}{" "}
              {query.data.page.total === 1 ? "attempt" : "attempts"}
            </span>
          )}
        </div>
      </div>

      <ol className="space-y-3">
        {query.data.page.items.map((call) => (
          <AICallRow
            key={call.id}
            competitionId={competitionId}
            generationId={generationId}
            summary={call}
          />
        ))}
      </ol>
      <div className="mt-5">
        <Pager
          label="AI attempts"
          page={page}
          totalPages={totalPages}
          total={query.data.page.total}
          onPageChange={setPage}
        />
      </div>
    </section>
  );
}
