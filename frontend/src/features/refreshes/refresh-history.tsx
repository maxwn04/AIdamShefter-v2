import { ArrowLeft, ArrowRight, CircleAlert } from "lucide-react";
import { useEffect } from "react";

import { ApiError } from "@/api/errors";
import { DateTime } from "@/components/shared/date-time";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { RefreshRun } from "@/features/refreshes/api";
import { useRefreshList } from "@/features/refreshes/queries";
import { RefreshStatusBadge } from "@/features/refreshes/status-badge";

const PAGE_SIZE = 20;

function RequestCounts({
  refresh,
}: {
  refresh: RefreshRun;
}): React.JSX.Element {
  return (
    <span>
      {refresh.succeeded_request_count}/{refresh.request_count} succeeded
      {refresh.failed_request_count > 0
        ? ` · ${String(refresh.failed_request_count)} failed`
        : ""}
    </span>
  );
}

function RefreshDetails({
  refresh,
}: {
  refresh: RefreshRun;
}): React.JSX.Element {
  return (
    <details>
      <summary className="cursor-pointer text-xs font-medium text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">
        Inspect stored details
      </summary>
      <div className="mt-3 space-y-3 rounded-md bg-muted/55 p-3 text-xs">
        <div>
          <p className="font-medium">Planned endpoint scopes</p>
          <ul className="mt-2 space-y-1 text-muted-foreground">
            {refresh.endpoint_scope.map((scope) => (
              <li key={scope.scope_key.value} className="break-all">
                {scope.scope_key.value} · {scope.endpoint_kind}
                {scope.required ? " · required" : " · optional"}
              </li>
            ))}
          </ul>
        </div>
        {refresh.error ? (
          <div>
            <p className="font-medium text-destructive">Recorded error</p>
            <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-background p-2 text-destructive">
              {JSON.stringify(refresh.error, null, 2)}
            </pre>
          </div>
        ) : null}
        <p className="leading-5 text-muted-foreground">
          Per-endpoint outcomes are returned immediately after a manual refresh;
          stored history currently retains the plan, aggregate counts, and safe
          refresh error only.
        </p>
      </div>
    </details>
  );
}

function DesktopHistory({ items }: { items: RefreshRun[] }): React.JSX.Element {
  return (
    <div className="hidden overflow-hidden rounded-lg border border-border bg-card md:block">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-muted/70 text-xs uppercase tracking-[0.1em] text-muted-foreground">
          <tr>
            <th className="px-5 py-3 font-semibold">Status</th>
            <th className="px-4 py-3 font-semibold">Trigger</th>
            <th className="px-4 py-3 font-semibold">Boundary</th>
            <th className="px-4 py-3 font-semibold">Started / completed</th>
            <th className="px-4 py-3 font-semibold">Requests</th>
            <th className="px-4 py-3 font-semibold">Audit</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((refresh) => (
            <tr key={refresh.id} className="align-top">
              <td className="px-5 py-4">
                <RefreshStatusBadge status={refresh.status} />
              </td>
              <td className="px-4 py-4 capitalize">{refresh.trigger}</td>
              <td className="px-4 py-4">
                {refresh.requested_through_week
                  ? `Week ${String(refresh.requested_through_week)}`
                  : "Derived"}
              </td>
              <td className="px-4 py-4">
                <div>
                  <DateTime value={refresh.started_at} />
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Completed:{" "}
                  <DateTime
                    value={refresh.completed_at}
                    empty="Still running"
                  />
                </div>
              </td>
              <td className="px-4 py-4 text-xs text-muted-foreground">
                <RequestCounts refresh={refresh} />
              </td>
              <td className="max-w-64 px-4 py-4">
                <RefreshDetails refresh={refresh} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MobileHistory({ items }: { items: RefreshRun[] }): React.JSX.Element {
  return (
    <div className="space-y-3 md:hidden">
      {items.map((refresh) => (
        <article
          key={refresh.id}
          className="rounded-lg border border-border bg-card p-4"
        >
          <div className="flex items-center justify-between gap-3">
            <RefreshStatusBadge status={refresh.status} />
            <span className="text-xs capitalize text-muted-foreground">
              {refresh.trigger}
            </span>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-xs text-muted-foreground">Boundary</dt>
              <dd className="mt-1">
                {refresh.requested_through_week
                  ? `Week ${String(refresh.requested_through_week)}`
                  : "Derived"}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Requests</dt>
              <dd className="mt-1">
                <RequestCounts refresh={refresh} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Started</dt>
              <dd className="mt-1">
                <DateTime value={refresh.started_at} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Completed</dt>
              <dd className="mt-1">
                <DateTime value={refresh.completed_at} empty="Still running" />
              </dd>
            </div>
          </dl>
          <div className="mt-4 border-t border-border pt-4">
            <RefreshDetails refresh={refresh} />
          </div>
        </article>
      ))}
    </div>
  );
}

export function RefreshHistory({
  competitionId,
  seasonId,
  page,
  onPageChange,
}: {
  competitionId: string;
  seasonId: string;
  page: number;
  onPageChange: (page: number) => void;
}): React.JSX.Element {
  const query = useRefreshList(competitionId, seasonId, {
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const totalPages = Math.max(
    1,
    Math.ceil((query.data?.page.total ?? 0) / PAGE_SIZE),
  );

  useEffect(() => {
    if (query.data && page > totalPages) onPageChange(totalPages);
  }, [onPageChange, page, query.data, totalPages]);

  if (query.isPending) {
    return (
      <div className="space-y-3" aria-label="Loading refresh history">
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
            : "Refresh history could not be loaded."}
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

  const items = query.data.page.items;
  if (items.length === 0 && page === 1) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-card/60 p-8 text-center">
        <p className="font-medium">No refreshes recorded</p>
        <p className="mt-2 text-sm text-muted-foreground">
          Manual, generation, scheduled, and backfill refreshes will appear
          here.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3 flex min-h-5 justify-end">
        {query.isFetching ? (
          <span className="text-xs text-muted-foreground" role="status">
            Updating…
          </span>
        ) : null}
      </div>
      <DesktopHistory items={items} />
      <MobileHistory items={items} />
      {query.data.page.total > PAGE_SIZE ? (
        <div className="mt-5 flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {page} of {totalPages} · {query.data.page.total} refreshes
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => {
                onPageChange(page - 1);
              }}
            >
              <ArrowLeft className="size-4" aria-hidden="true" /> Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => {
                onPageChange(page + 1);
              }}
            >
              Next <ArrowRight className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
