import { CircleAlert, Clock3, Coins, Cpu } from "lucide-react";

import { ApiError } from "@/api/errors";
import { DateTime } from "@/components/shared/date-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ModelUsageBreakdown, TokenTotals } from "@/features/usage/api";
import { useGenerationUsage } from "@/features/usage/queries";

interface UsagePanelProps {
  competitionId: string;
  generationId: string;
  active: boolean;
  provisional: boolean;
}

function numberLabel(value: number): string {
  return value.toLocaleString();
}

function costLabel(value: string | null, currency: string): string {
  return value === null ? "Unavailable" : `${currency} ${value}`;
}

function modelLabel(breakdown: ModelUsageBreakdown): string {
  const identity = [breakdown.provider, breakdown.model]
    .filter(Boolean)
    .join(" / ");
  return identity || "Provider or model not recorded";
}

function TokenSummary({ tokens }: { tokens: TokenTotals }): React.JSX.Element {
  const categories = [
    { label: "Input", value: tokens.input_tokens },
    { label: "Cached input", value: tokens.cached_input_tokens },
    { label: "Output", value: tokens.output_tokens },
    { label: "Reasoning", value: tokens.reasoning_tokens },
    { label: "Total", value: tokens.total_tokens },
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 xl:grid-cols-5">
      {categories.map((category) => (
        <div key={category.label}>
          <dt className="text-xs text-muted-foreground">{category.label}</dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums">
            {numberLabel(category.value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function BreakdownTable({
  breakdowns,
}: {
  breakdowns: ModelUsageBreakdown[];
}): React.JSX.Element {
  return (
    <div className="hidden overflow-hidden rounded-lg border border-border lg:block">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-muted/70 text-xs uppercase tracking-[0.1em] text-muted-foreground">
          <tr>
            <th className="px-4 py-3 font-semibold">Provider / model</th>
            <th className="px-4 py-3 font-semibold">Attempts</th>
            <th className="px-4 py-3 font-semibold">Tokens</th>
            <th className="px-4 py-3 font-semibold">Latency</th>
            <th className="px-4 py-3 font-semibold">Estimated cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {breakdowns.map((breakdown, index) => (
            <tr
              key={`${breakdown.provider ?? "unknown"}:${breakdown.model ?? "unknown"}:${String(index)}`}
            >
              <td className="max-w-64 px-4 py-4">
                <p className="break-all font-medium">{modelLabel(breakdown)}</p>
                {!breakdown.complete ? (
                  <Badge className="mt-2" variant="secondary">
                    Incomplete
                  </Badge>
                ) : null}
              </td>
              <td className="px-4 py-4 font-mono tabular-nums">
                {numberLabel(breakdown.attempt_count)}
              </td>
              <td className="px-4 py-4 font-mono tabular-nums">
                {numberLabel(breakdown.tokens.total_tokens)}
              </td>
              <td className="px-4 py-4 font-mono tabular-nums">
                {numberLabel(breakdown.latency_ms)} ms
              </td>
              <td className="px-4 py-4 font-mono tabular-nums">
                {costLabel(breakdown.estimated_cost, breakdown.currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BreakdownCards({
  breakdowns,
}: {
  breakdowns: ModelUsageBreakdown[];
}): React.JSX.Element {
  return (
    <div className="space-y-3 lg:hidden">
      {breakdowns.map((breakdown, index) => (
        <article
          key={`${breakdown.provider ?? "unknown"}:${breakdown.model ?? "unknown"}:${String(index)}`}
          className="rounded-lg border border-border bg-card p-4"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <h4 className="break-all font-medium">{modelLabel(breakdown)}</h4>
            {!breakdown.complete ? (
              <Badge variant="secondary">Incomplete</Badge>
            ) : null}
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-border pt-4 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">Attempts</dt>
              <dd className="mt-1 font-mono tabular-nums">
                {numberLabel(breakdown.attempt_count)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Tokens</dt>
              <dd className="mt-1 font-mono tabular-nums">
                {numberLabel(breakdown.tokens.total_tokens)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Latency</dt>
              <dd className="mt-1 font-mono tabular-nums">
                {numberLabel(breakdown.latency_ms)} ms
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Estimated cost</dt>
              <dd className="mt-1 break-all font-mono tabular-nums">
                {costLabel(breakdown.estimated_cost, breakdown.currency)}
              </dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

function AffectedCalls({
  title,
  ids,
}: {
  title: string;
  ids: string[];
}): React.JSX.Element | null {
  if (ids.length === 0) return null;
  return (
    <div>
      <h4 className="text-sm font-medium">{title}</h4>
      <ul className="mt-2 max-h-40 space-y-1 overflow-y-auto rounded-md border border-border bg-background p-3">
        {ids.map((id) => (
          <li key={id} className="break-all font-mono text-xs">
            {id}
          </li>
        ))}
      </ul>
    </div>
  );
}

function UsageSkeleton(): React.JSX.Element {
  return (
    <div className="space-y-6">
      <Skeleton className="h-36 w-full rounded-lg" />
      <Skeleton className="h-64 w-full rounded-lg" />
    </div>
  );
}

export function UsagePanel({
  competitionId,
  generationId,
  active,
  provisional,
}: UsagePanelProps): React.JSX.Element {
  const usageQuery = useGenerationUsage(
    competitionId,
    generationId,
    active,
    provisional,
  );

  if (!active) return <></>;
  if (usageQuery.isPending) return <UsageSkeleton />;

  if (usageQuery.isError) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
        <CircleAlert className="size-6 text-destructive" aria-hidden="true" />
        <h3 className="mt-3 font-semibold">Usage unavailable</h3>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {usageQuery.error instanceof ApiError
            ? usageQuery.error.message
            : "The aggregate generation usage could not be loaded."}
        </p>
        <Button
          className="mt-4"
          variant="outline"
          onClick={() => void usageQuery.refetch()}
        >
          Try again
        </Button>
      </div>
    );
  }

  const usage = usageQuery.data.usage;
  const incomplete = !usage.complete;

  return (
    <div className="min-w-0 space-y-6">
      {provisional ? (
        <div className="rounded-lg border border-primary/25 bg-primary/5 p-4 text-sm leading-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">Provisional</Badge>
            <span className="font-medium">This run is still active.</span>
          </div>
          <p className="mt-2 text-muted-foreground">
            Recorded attempts are included now. Totals and the current estimate
            may change as more calls finish.
          </p>
        </div>
      ) : null}

      {incomplete ? (
        <section
          className="rounded-lg border border-destructive/30 bg-destructive/5 p-5"
          aria-labelledby="incomplete-usage-heading"
        >
          <div className="flex items-start gap-3">
            <CircleAlert
              className="mt-0.5 size-5 shrink-0 text-destructive"
              aria-hidden="true"
            />
            <div>
              <h3 id="incomplete-usage-heading" className="font-semibold">
                Estimate is incomplete
              </h3>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                One or more attempts lacked reported usage or current pricing.
                Unavailable cost is not treated as zero.
              </p>
            </div>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <AffectedCalls
              title="Calls missing usage"
              ids={usage.missing_usage_call_ids}
            />
            <AffectedCalls
              title="Calls without current pricing"
              ids={usage.unpriced_call_ids}
            />
          </div>
        </section>
      ) : null}

      <section
        className="rounded-lg border border-border bg-card p-5 sm:p-6"
        aria-labelledby="usage-summary-heading"
      >
        <div className="flex flex-col gap-5 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Coins
                className="size-5 text-muted-foreground"
                aria-hidden="true"
              />
              <h3
                id="usage-summary-heading"
                className="font-editorial text-2xl font-semibold"
              >
                Usage summary
              </h3>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              All recorded provider attempts, including fallbacks and failures
              when usage was reported.
            </p>
          </div>
          <div className="sm:text-right">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              Estimated cost
            </p>
            <p className="mt-1 break-all font-mono text-2xl font-semibold tabular-nums">
              {costLabel(usage.estimated_cost, usage.currency)}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Current quote · <DateTime value={usage.quoted_at} showExact />
            </p>
          </div>
        </div>

        <div className="pt-5">
          <TokenSummary tokens={usage.tokens} />
        </div>
        <dl className="mt-6 grid gap-4 border-t border-border pt-5 text-sm sm:grid-cols-2">
          <div className="flex items-center gap-3">
            <Cpu className="size-4 text-muted-foreground" aria-hidden="true" />
            <div>
              <dt className="text-xs text-muted-foreground">Attempts</dt>
              <dd className="mt-1 font-mono font-medium tabular-nums">
                {numberLabel(usage.attempt_count)}
              </dd>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Clock3
              className="size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <div>
              <dt className="text-xs text-muted-foreground">
                Aggregate latency
              </dt>
              <dd className="mt-1 font-mono font-medium tabular-nums">
                {numberLabel(usage.latency_ms)} ms
              </dd>
            </div>
          </div>
        </dl>
      </section>

      <section aria-labelledby="model-usage-heading">
        <div className="mb-4 flex items-end justify-between gap-3">
          <div>
            <h3
              id="model-usage-heading"
              className="font-editorial text-2xl font-semibold"
            >
              Provider and model breakdown
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Backend-recorded actual provider/model usage and current estimate.
            </p>
          </div>
          <span className="text-xs text-muted-foreground">
            {usage.breakdowns.length} model group
            {usage.breakdowns.length === 1 ? "" : "s"}
          </span>
        </div>
        {usage.breakdowns.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-card/60 p-7 text-sm text-muted-foreground">
            No provider/model usage has been recorded for this run.
          </div>
        ) : (
          <>
            <BreakdownTable breakdowns={usage.breakdowns} />
            <BreakdownCards breakdowns={usage.breakdowns} />
          </>
        )}
      </section>
    </div>
  );
}
