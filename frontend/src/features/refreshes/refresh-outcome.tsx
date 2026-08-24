import { AlertTriangle, CheckCircle2, CircleX } from "lucide-react";

import { DateTime } from "@/components/shared/date-time";
import type { ManualRefreshResponse } from "@/features/refreshes/api";
import { RefreshStatusBadge } from "@/features/refreshes/status-badge";
import { cn } from "@/lib/utils";

export function RefreshOutcomePanel({
  outcome,
}: {
  outcome: ManualRefreshResponse;
}): React.JSX.Element {
  const status = outcome.refresh.status;
  const Icon =
    status === "succeeded"
      ? CheckCircle2
      : status === "partial"
        ? AlertTriangle
        : CircleX;

  return (
    <section
      className={cn(
        "mt-8 rounded-lg border p-5",
        status === "succeeded" && "border-primary/30 bg-primary/5",
        status === "partial" && "border-border bg-accent/60",
        status === "failed" && "border-destructive/30 bg-destructive/5",
      )}
      aria-labelledby="latest-refresh-outcome"
    >
      <div className="flex items-start gap-3">
        <Icon
          className={cn(
            "mt-0.5 size-5 shrink-0",
            status === "failed" ? "text-destructive" : "text-primary",
          )}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h2
              id="latest-refresh-outcome"
              className="font-editorial text-xl font-semibold"
            >
              Latest manual refresh outcome
            </h2>
            <RefreshStatusBadge status={status} />
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            Effective through week{" "}
            {outcome.effective_through_week ?? "not available"} · completed{" "}
            <DateTime value={outcome.refresh.completed_at} />
          </p>
          <p className="mt-3 text-sm">
            {outcome.refresh.succeeded_request_count} of{" "}
            {outcome.refresh.request_count} requests succeeded;{" "}
            {outcome.refresh.failed_request_count} failed.
          </p>
        </div>
      </div>

      {outcome.scope_results.length > 0 ? (
        <details className="mt-5 border-t border-border pt-4">
          <summary className="cursor-pointer text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Inspect endpoint results
          </summary>
          <ul className="mt-3 space-y-2">
            {outcome.scope_results.map((result) => (
              <li
                key={result.api_request_id}
                className="rounded-md bg-background/70 p-3 text-xs"
              >
                <p className="break-all font-medium">
                  {result.scope_key.value}
                </p>
                <p className="mt-1 text-muted-foreground">
                  Fetch: {result.fetch_status} · normalization:{" "}
                  {result.normalization_status} ·{" "}
                  {result.changed_current_view
                    ? "current view changed"
                    : "current view unchanged"}
                </p>
                {result.warning_codes.length > 0 ? (
                  <p className="mt-1 text-muted-foreground">
                    Warnings: {result.warning_codes.join(", ")}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {outcome.refresh.error ? (
        <details className="mt-4 border-t border-border pt-4">
          <summary className="cursor-pointer text-sm font-medium text-destructive outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Inspect recorded error
          </summary>
          <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-background/80 p-3 text-xs text-destructive">
            {JSON.stringify(outcome.refresh.error, null, 2)}
          </pre>
        </details>
      ) : null}
    </section>
  );
}
