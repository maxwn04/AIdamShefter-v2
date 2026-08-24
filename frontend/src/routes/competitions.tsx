import {
  Archive,
  ArrowLeft,
  ArrowRight,
  CircleAlert,
  MoreHorizontal,
  Trophy,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { ApiError } from "@/api/errors";
import { DateTime } from "@/components/shared/date-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { ArchiveCompetitionDialog } from "@/features/competitions/archive-competition-dialog";
import type {
  Competition,
  CompetitionOverview,
} from "@/features/competitions/api";
import { CreateCompetitionDialog } from "@/features/competitions/create-competition-dialog";
import { useCompetitionList } from "@/features/competitions/queries";

const PAGE_SIZE = 50;

function positivePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function attention(summary: CompetitionOverview["summary"]): {
  label: string;
  variant: "secondary" | "outline" | "destructive";
} {
  if (summary.season_count === 0)
    return { label: "Needs a season", variant: "secondary" };
  if (!summary.latest_terminal_refresh)
    return { label: "Never refreshed", variant: "outline" };
  if (summary.latest_terminal_refresh.status === "partial")
    return { label: "Latest refresh partial", variant: "secondary" };
  if (summary.latest_terminal_refresh.status === "failed")
    return { label: "Latest refresh failed", variant: "destructive" };
  if (summary.latest_terminal_refresh.status === "cancelled")
    return { label: "Refresh cancelled", variant: "outline" };
  return { label: "Refreshed", variant: "outline" };
}

function RowActions({
  competition,
  onArchive,
}: {
  competition: Competition;
  onArchive: (competition: Competition) => void;
}): React.JSX.Element {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Actions for ${competition.display_name}`}
        >
          <MoreHorizontal className="size-4" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem
          className="text-destructive data-[highlighted]:text-destructive"
          onSelect={() => {
            onArchive(competition);
          }}
        >
          <Archive className="size-4" aria-hidden="true" />
          Archive competition
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function DesktopTable({
  items,
  onArchive,
}: {
  items: CompetitionOverview[];
  onArchive: (competition: Competition) => void;
}): React.JSX.Element {
  return (
    <div className="hidden overflow-hidden rounded-lg border border-border bg-card md:block">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-muted/70 text-xs uppercase tracking-[0.1em] text-muted-foreground">
          <tr>
            <th className="px-5 py-3 font-semibold">League</th>
            <th className="px-4 py-3 font-semibold">Seasons</th>
            <th className="px-4 py-3 font-semibold">Last successful refresh</th>
            <th className="px-4 py-3 font-semibold">Latest article</th>
            <th className="px-4 py-3 font-semibold">Attention</th>
            <th className="w-12 px-3 py-3">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map(({ competition, summary }) => {
            const state = attention(summary);
            return (
              <tr key={competition.id} className="hover:bg-muted/35">
                <td className="px-5 py-4">
                  <Link
                    className="font-editorial text-lg font-semibold hover:underline"
                    to={`/competitions/${competition.id}`}
                  >
                    {competition.display_name}
                  </Link>
                </td>
                <td className="px-4 py-4">
                  <span className="font-medium">{summary.season_count}</span>
                  <span className="ml-2 text-muted-foreground">
                    {summary.latest_season
                      ? `Latest ${String(summary.latest_season.season_year)}`
                      : "No seasons"}
                  </span>
                </td>
                <td className="px-4 py-4">
                  <DateTime value={summary.latest_successful_refresh_at} />
                </td>
                <td className="px-4 py-4">
                  <DateTime value={summary.latest_submitted_article_at} />
                </td>
                <td className="px-4 py-4">
                  <Badge variant={state.variant}>{state.label}</Badge>
                </td>
                <td className="px-3 py-4">
                  <RowActions competition={competition} onArchive={onArchive} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function MobileCards({
  items,
  onArchive,
}: {
  items: CompetitionOverview[];
  onArchive: (competition: Competition) => void;
}): React.JSX.Element {
  return (
    <div className="space-y-3 md:hidden">
      {items.map(({ competition, summary }) => {
        const state = attention(summary);
        return (
          <article
            key={competition.id}
            className="rounded-lg border border-border bg-card p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <Link
                  className="font-editorial text-xl font-semibold hover:underline"
                  to={`/competitions/${competition.id}`}
                >
                  {competition.display_name}
                </Link>
                <p className="mt-1 text-sm text-muted-foreground">
                  {summary.season_count === 0
                    ? "No seasons"
                    : `${String(summary.season_count)} season${summary.season_count === 1 ? "" : "s"} · latest ${String(summary.latest_season?.season_year ?? "")}`}
                </p>
              </div>
              <RowActions competition={competition} onArchive={onArchive} />
            </div>
            <Badge className="mt-4" variant={state.variant}>
              {state.label}
            </Badge>
            <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-border pt-4 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground">
                  Last successful refresh
                </dt>
                <dd className="mt-1">
                  <DateTime value={summary.latest_successful_refresh_at} />
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">
                  Latest article
                </dt>
                <dd className="mt-1">
                  <DateTime value={summary.latest_submitted_article_at} />
                </dd>
              </div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function CatalogSkeleton(): React.JSX.Element {
  return (
    <div className="space-y-3" aria-label="Loading leagues">
      {[0, 1, 2].map((item) => (
        <Skeleton key={item} className="h-24 w-full rounded-lg" />
      ))}
    </div>
  );
}

export function Component(): React.JSX.Element {
  const [searchParameters, setSearchParameters] = useSearchParams();
  const page = positivePage(searchParameters.get("page"));
  const [archiveCandidate, setArchiveCandidate] = useState<Competition | null>(
    null,
  );
  const query = useCompetitionList({
    includeArchived: false,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const totalPages = Math.max(
    1,
    Math.ceil((query.data?.page.total ?? 0) / PAGE_SIZE),
  );

  useEffect(() => {
    if (query.data && page > totalPages) {
      setSearchParameters(
        totalPages === 1 ? {} : { page: String(totalPages) },
        { replace: true },
      );
    }
  }, [page, query.data, setSearchParameters, totalPages]);

  function setPage(nextPage: number): void {
    setSearchParameters(nextPage === 1 ? {} : { page: String(nextPage) });
  }

  const items = query.data?.page.items ?? [];

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <header className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            League desk
          </p>
          <h1 className="mt-3 font-editorial text-4xl font-semibold tracking-tight sm:text-5xl">
            Leagues
          </h1>
          <p className="mt-4 text-base leading-7 text-muted-foreground">
            Manage each competition as one continuous league identity across its
            Sleeper seasons.
          </p>
        </div>
        <CreateCompetitionDialog />
      </header>

      <section className="mt-10" aria-labelledby="competition-list-heading">
        <div className="mb-4 flex min-h-6 items-center justify-between gap-3">
          <h2
            id="competition-list-heading"
            className="font-editorial text-xl font-semibold"
          >
            Active competitions
          </h2>
          {query.isFetching && !query.isPending ? (
            <span className="text-xs text-muted-foreground" role="status">
              Updating…
            </span>
          ) : null}
        </div>

        {query.isPending ? <CatalogSkeleton /> : null}

        {query.isError ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
            <CircleAlert
              className="size-6 text-destructive"
              aria-hidden="true"
            />
            <h3 className="mt-3 font-semibold">League catalog unavailable</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              {query.error instanceof ApiError
                ? query.error.message
                : "The league catalog could not be loaded."}
            </p>
            <Button
              className="mt-4"
              variant="outline"
              onClick={() => void query.refetch()}
            >
              Try again
            </Button>
          </div>
        ) : null}

        {query.isSuccess && items.length === 0 && page === 1 ? (
          <div className="rounded-lg border border-dashed border-border bg-card/60 p-8 text-center sm:p-12">
            <div className="mx-auto flex size-12 items-center justify-center rounded-full border border-border bg-background">
              <Trophy
                className="size-5 text-muted-foreground"
                aria-hidden="true"
              />
            </div>
            <h3 className="mt-5 font-editorial text-2xl font-semibold">
              Create your first competition
            </h3>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
              A competition connects the same fantasy league across years.
              Create it now, then attach its first Sleeper season.
            </p>
            <div className="mt-6 flex justify-center">
              <CreateCompetitionDialog prominent />
            </div>
          </div>
        ) : null}

        {query.isSuccess && items.length > 0 ? (
          <>
            <DesktopTable items={items} onArchive={setArchiveCandidate} />
            <MobileCards items={items} onArchive={setArchiveCandidate} />
            {query.data.page.total > PAGE_SIZE ? (
              <div className="mt-5 flex items-center justify-between text-sm">
                <span className="text-muted-foreground">
                  Page {page} of {totalPages} · {query.data.page.total} leagues
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => {
                      setPage(page - 1);
                    }}
                  >
                    <ArrowLeft className="size-4" aria-hidden="true" /> Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => {
                      setPage(page + 1);
                    }}
                  >
                    Next <ArrowRight className="size-4" aria-hidden="true" />
                  </Button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </section>

      <ArchiveCompetitionDialog
        competition={archiveCandidate}
        onOpenChange={(open) => {
          if (!open) setArchiveCandidate(null);
        }}
      />
    </div>
  );
}
