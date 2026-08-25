import { CircleAlert } from "lucide-react";
import { Link } from "react-router";

import { ApiError } from "@/api/errors";
import type { components } from "@/api/generated/schema";
import { DateTime } from "@/components/shared/date-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useGenerationHistory } from "@/features/generations/queries";

type GenerationSummary = components["schemas"]["GenerationSummary"];

function titleCase(value: string): string {
  return value
    .split(/[_\-.\s]+/u)
    .filter(Boolean)
    .map((part) => `${part[0]?.toUpperCase() ?? ""}${part.slice(1)}`)
    .join(" ");
}

function statusVariant(
  status: GenerationSummary["status"],
): "default" | "outline" | "secondary" | "destructive" {
  if (status === "failed") return "destructive";
  if (status === "succeeded") return "default";
  if (status === "running") return "secondary";
  return "outline";
}

function weekLabel(run: GenerationSummary): string {
  if (run.week_start === null || run.week_end === null) {
    return "Weeks not resolved";
  }
  if (run.week_start === run.week_end) return `Week ${String(run.week_start)}`;
  return `Weeks ${String(run.week_start)}–${String(run.week_end)}`;
}

function RunTime({ run }: { run: GenerationSummary }): React.JSX.Element {
  const label = run.completed_at
    ? "Completed"
    : run.started_at
      ? "Started"
      : "Created";
  const value = run.completed_at ?? run.started_at ?? run.created_at;
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="mt-1">
        <DateTime value={value} />
      </div>
    </div>
  );
}

function RunProgress({ run }: { run: GenerationSummary }): React.JSX.Element {
  if (run.failure_summary) {
    return (
      <div>
        <p className="break-words text-sm text-destructive">
          {run.failure_summary}
        </p>
        {run.failure_category ? (
          <p className="mt-1 break-all font-mono text-xs text-muted-foreground">
            {run.failure_category}
          </p>
        ) : null}
      </div>
    );
  }

  if (run.status === "pending") {
    return <span className="text-sm text-muted-foreground">Queued</span>;
  }

  if (run.current_stage) {
    return (
      <div>
        <p className="break-words text-sm">{titleCase(run.current_stage)}</p>
        {run.status === "running" ? (
          <p className="mt-1 text-xs text-muted-foreground">
            Turn {String(run.current_turn)}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <span className="text-sm text-muted-foreground">No stage recorded</span>
  );
}

function DesktopRuns({
  competitionId,
  items,
}: {
  competitionId: string;
  items: GenerationSummary[];
}): React.JSX.Element {
  return (
    <div className="hidden overflow-hidden rounded-lg border border-border bg-card md:block">
      <table className="w-full table-fixed border-collapse text-left text-sm">
        <thead className="bg-muted/70 text-xs uppercase tracking-[0.1em] text-muted-foreground">
          <tr>
            <th className="w-32 px-5 py-3 font-semibold">Status</th>
            <th className="w-36 px-4 py-3 font-semibold">Scope</th>
            <th className="px-4 py-3 font-semibold">Assignment</th>
            <th className="w-48 px-4 py-3 font-semibold">Stage</th>
            <th className="w-36 px-4 py-3 font-semibold">Time</th>
            <th className="w-24 px-4 py-3 text-right font-semibold">Run</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((run) => (
            <tr key={run.id} className="align-top">
              <td className="px-5 py-4">
                <Badge variant={statusVariant(run.status)}>
                  {titleCase(run.status)}
                </Badge>
              </td>
              <td className="px-4 py-4">
                <p className="font-medium">{titleCase(run.kind)}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {weekLabel(run)}
                </p>
              </td>
              <td className="min-w-0 px-4 py-4">
                <p className="line-clamp-2 break-words leading-6">
                  {run.request_text}
                </p>
              </td>
              <td className="min-w-0 px-4 py-4">
                <RunProgress run={run} />
              </td>
              <td className="px-4 py-4">
                <RunTime run={run} />
              </td>
              <td className="px-4 py-4 text-right">
                <Link
                  className="font-medium text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
                  to={`/competitions/${competitionId}/generations/${run.id}`}
                >
                  Open
                  <span className="sr-only"> generation run</span>
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MobileRuns({
  competitionId,
  items,
}: {
  competitionId: string;
  items: GenerationSummary[];
}): React.JSX.Element {
  return (
    <div className="space-y-3 md:hidden">
      {items.map((run) => (
        <article
          key={run.id}
          className="min-w-0 overflow-hidden rounded-lg border border-border bg-card p-4"
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={statusVariant(run.status)}>
              {titleCase(run.status)}
            </Badge>
            <Badge variant="outline">{titleCase(run.kind)}</Badge>
            <span className="text-xs text-muted-foreground">
              {weekLabel(run)}
            </span>
          </div>
          <p className="mt-4 line-clamp-3 break-words text-sm leading-6">
            {run.request_text}
          </p>
          <div className="mt-4 border-t border-border pt-4">
            <RunProgress run={run} />
          </div>
          <div className="mt-4 flex flex-wrap items-end justify-between gap-4 border-t border-border pt-4">
            <RunTime run={run} />
            <Link
              className="font-medium text-primary underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
              to={`/competitions/${competitionId}/generations/${run.id}`}
            >
              Open run
            </Link>
          </div>
        </article>
      ))}
    </div>
  );
}

export function RecentRuns({
  competitionId,
  seasonId,
}: {
  competitionId: string;
  seasonId: string;
}): React.JSX.Element {
  const query = useGenerationHistory(competitionId, seasonId, 5);

  if (query.isPending) {
    return (
      <div className="space-y-3" aria-label="Loading recent generation runs">
        {[0, 1, 2].map((item) => (
          <Skeleton key={item} className="h-24 w-full rounded-lg" />
        ))}
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
        <CircleAlert className="size-6 text-destructive" aria-hidden="true" />
        <p className="mt-3 text-sm text-destructive">
          {query.error instanceof ApiError
            ? query.error.message
            : "Recent generation runs could not be loaded."}
        </p>
        <Button
          className="mt-4"
          variant="outline"
          onClick={() => void query.refetch()}
        >
          Try again
        </Button>
      </div>
    );
  }

  const items = query.data.page.items.slice(0, 5);
  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-card/60 p-8 text-center">
        <p className="font-medium">No generation runs recorded</p>
        <p className="mt-2 text-sm text-muted-foreground">
          Live and historical runs for this season will appear here after they
          are submitted.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3 flex min-h-5 items-center justify-between gap-4">
        <span className="text-xs text-muted-foreground">
          Showing {String(items.length)} newest
          {query.data.page.total > items.length
            ? ` of ${String(query.data.page.total)}`
            : ""}
        </span>
        {query.isFetching ? (
          <span className="text-xs text-muted-foreground" role="status">
            Updating…
          </span>
        ) : null}
      </div>
      <DesktopRuns competitionId={competitionId} items={items} />
      <MobileRuns competitionId={competitionId} items={items} />
    </div>
  );
}
