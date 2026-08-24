import { CircleAlert, Database, RefreshCw, Trophy } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router";

import { ApiError } from "@/api/errors";
import { DateTime } from "@/components/shared/date-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCompetitionDetail } from "@/features/competitions/queries";
import type { ManualRefreshResponse } from "@/features/refreshes/api";
import { RefreshHistory } from "@/features/refreshes/refresh-history";
import { RefreshOutcomePanel } from "@/features/refreshes/refresh-outcome";
import { RefreshSheet } from "@/features/refreshes/refresh-sheet";
import { RosterMappingPanel } from "@/features/roster-mappings/roster-mapping-panel";
import { AddSeasonDialog } from "@/features/seasons/add-season-dialog";
import type { CompetitionSeasonOverview } from "@/features/seasons/api";
import { useSeasonDetail, useSeasonList } from "@/features/seasons/queries";
import { cn } from "@/lib/utils";

const seasonListParameters = { limit: 200, offset: 0 } as const;

function positivePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function refreshBadge(status: string): {
  label: string;
  variant: "outline" | "secondary" | "destructive";
} {
  if (status === "succeeded") return { label: "Succeeded", variant: "outline" };
  if (status === "partial") return { label: "Partial", variant: "secondary" };
  if (status === "failed") return { label: "Failed", variant: "destructive" };
  if (status === "running") return { label: "Running", variant: "secondary" };
  return { label: "Cancelled", variant: "outline" };
}

function RefreshSummary({
  summary,
}: {
  summary: CompetitionSeasonOverview["summary"];
}): React.JSX.Element {
  const refresh = summary.latest_terminal_refresh;
  if (!refresh) {
    return (
      <span className="text-sm text-muted-foreground">Never refreshed</span>
    );
  }
  const badge = refreshBadge(refresh.status);
  return (
    <div className="space-y-1">
      <Badge variant={badge.variant}>{badge.label}</Badge>
      <p className="text-xs text-muted-foreground">
        <DateTime value={refresh.completed_at} />
        {refresh.requested_through_week
          ? ` · through week ${String(refresh.requested_through_week)}`
          : " · derived boundary"}
      </p>
      <p className="text-xs text-muted-foreground">
        {refresh.succeeded_request_count}/{refresh.request_count} requests
        succeeded
      </p>
    </div>
  );
}

function SeasonTable({
  items,
  selectedSeasonId,
  onSelect,
}: {
  items: CompetitionSeasonOverview[];
  selectedSeasonId?: string;
  onSelect: (seasonId: string) => void;
}): React.JSX.Element {
  return (
    <div className="hidden overflow-hidden rounded-lg border border-border bg-card lg:block">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-muted/70 text-xs uppercase tracking-[0.1em] text-muted-foreground">
          <tr>
            <th className="px-5 py-3 font-semibold">Season</th>
            <th className="px-4 py-3 font-semibold">Sleeper identity</th>
            <th className="px-4 py-3 font-semibold">Latest refresh</th>
            <th className="px-4 py-3 font-semibold">Last successful</th>
            <th className="px-4 py-3 font-semibold">Generation snapshot</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map(({ season, summary }) => (
            <tr
              key={season.id}
              className={cn(
                "hover:bg-muted/35",
                selectedSeasonId === season.id && "bg-accent/55",
              )}
            >
              <td className="px-5 py-4">
                <button
                  type="button"
                  className="text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-current={
                    selectedSeasonId === season.id ? "true" : undefined
                  }
                  onClick={() => {
                    onSelect(season.id);
                  }}
                >
                  <span className="font-editorial text-lg font-semibold">
                    {season.season_year}
                  </span>
                  <span className="ml-2 text-xs text-muted-foreground">
                    #{season.sequence_number}
                  </span>
                </button>
              </td>
              <td className="px-4 py-4">
                <p className="font-medium">
                  {summary.league_name ?? "Not loaded"}
                </p>
                <p
                  className="mt-1 max-w-52 truncate text-xs text-muted-foreground"
                  title={season.sleeper_league_id}
                >
                  {season.sleeper_league_id}
                </p>
                {summary.league_status ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Status: {summary.league_status}
                  </p>
                ) : null}
              </td>
              <td className="px-4 py-4">
                <RefreshSummary summary={summary} />
              </td>
              <td className="px-4 py-4">
                <DateTime value={summary.latest_successful_refresh_at} />
              </td>
              <td className="px-4 py-4">
                <DateTime
                  value={summary.latest_ready_snapshot_at}
                  empty="None built"
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SeasonCards({
  items,
  selectedSeasonId,
  onSelect,
}: {
  items: CompetitionSeasonOverview[];
  selectedSeasonId?: string;
  onSelect: (seasonId: string) => void;
}): React.JSX.Element {
  return (
    <div className="space-y-3 lg:hidden">
      {items.map(({ season, summary }) => (
        <article
          key={season.id}
          className={cn(
            "rounded-lg border border-border bg-card p-4",
            selectedSeasonId === season.id && "border-primary/50 bg-accent/45",
          )}
        >
          <button
            type="button"
            className="w-full text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-current={selectedSeasonId === season.id ? "true" : undefined}
            onClick={() => {
              onSelect(season.id);
            }}
          >
            <span className="font-editorial text-xl font-semibold">
              {season.season_year}
            </span>
            <span className="ml-2 text-xs text-muted-foreground">
              Season #{season.sequence_number}
            </span>
            <span className="mt-1 block text-sm font-medium">
              {summary.league_name ?? "Sleeper data not loaded"}
            </span>
            <span className="mt-1 block break-all text-xs text-muted-foreground">
              {season.sleeper_league_id}
            </span>
          </button>
          <div className="mt-4 border-t border-border pt-4">
            <RefreshSummary summary={summary} />
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-xs">
            <div>
              <dt className="text-muted-foreground">Last successful</dt>
              <dd className="mt-1 text-sm">
                <DateTime value={summary.latest_successful_refresh_at} />
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Generation snapshot</dt>
              <dd className="mt-1 text-sm">
                <DateTime
                  value={summary.latest_ready_snapshot_at}
                  empty="None built"
                />
              </dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

function OverviewSkeleton(): React.JSX.Element {
  return (
    <div className="mx-auto max-w-6xl space-y-8 px-5 py-10 sm:px-8 sm:py-14">
      <Skeleton className="h-12 w-72" />
      <Skeleton className="h-64 w-full" />
      <Skeleton className="h-56 w-full" />
    </div>
  );
}

export function Component(): React.JSX.Element {
  const { competitionId } = useParams();
  const [searchParameters, setSearchParameters] = useSearchParams();
  const [latestOutcome, setLatestOutcome] = useState<{
    seasonId: string;
    outcome: ManualRefreshResponse;
  }>();
  const competitionQuery = useCompetitionDetail(competitionId);
  const seasonsQuery = useSeasonList(competitionId, seasonListParameters);
  const seasons = seasonsQuery.data?.page.items ?? [];
  const requestedSeasonId = searchParameters.get("season") ?? undefined;
  const refreshPage = positivePage(searchParameters.get("refreshPage"));
  const requestedSeason = seasons.find(
    ({ season }) => season.id === requestedSeasonId,
  );
  const selectedSeasonId = requestedSeason?.season.id ?? seasons[0]?.season.id;
  const selectedSeason = seasons.find(
    ({ season }) => season.id === selectedSeasonId,
  );
  const seasonDetailQuery = useSeasonDetail(competitionId, selectedSeasonId);

  useEffect(() => {
    if (!seasonsQuery.isSuccess) return;
    if (requestedSeasonId === selectedSeasonId) return;
    const next = new URLSearchParams(searchParameters);
    if (selectedSeasonId) next.set("season", selectedSeasonId);
    else next.delete("season");
    next.delete("refreshPage");
    setSearchParameters(next, { replace: true });
  }, [
    requestedSeasonId,
    searchParameters,
    seasonsQuery.isSuccess,
    selectedSeasonId,
    setSearchParameters,
  ]);

  function selectSeason(seasonId: string): void {
    const next = new URLSearchParams(searchParameters);
    next.set("season", seasonId);
    next.delete("refreshPage");
    setSearchParameters(next);
  }

  const setRefreshPage = useCallback(
    (page: number): void => {
      const next = new URLSearchParams(searchParameters);
      if (page === 1) next.delete("refreshPage");
      else next.set("refreshPage", String(page));
      setSearchParameters(next);
    },
    [searchParameters, setSearchParameters],
  );

  if (competitionQuery.isPending || seasonsQuery.isPending)
    return <OverviewSkeleton />;

  if (competitionQuery.isError || seasonsQuery.isError) {
    const error = competitionQuery.error ?? seasonsQuery.error;
    const missing = error instanceof ApiError && error.status === 404;
    return (
      <div className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
        <CircleAlert className="size-8 text-destructive" aria-hidden="true" />
        <h1 className="mt-4 font-editorial text-3xl font-semibold">
          {missing ? "League not found" : "League overview unavailable"}
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          {error instanceof ApiError
            ? error.message
            : "The competition and its seasons could not be loaded."}
        </p>
        <Button
          className="mt-6"
          variant="outline"
          onClick={() => {
            void Promise.all([
              competitionQuery.refetch(),
              seasonsQuery.refetch(),
            ]);
          }}
        >
          Try again
        </Button>
      </div>
    );
  }

  const competition = competitionQuery.data.competition;
  const archived = competition.archived_at !== null;
  const detail = seasonDetailQuery.data;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <header className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Competition overview
            </p>
            {archived ? <Badge variant="outline">Archived</Badge> : null}
          </div>
          <h1 className="mt-3 font-editorial text-4xl font-semibold tracking-tight sm:text-5xl">
            {competition.display_name}
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            {seasons.length === 0
              ? "Attach a Sleeper season to begin managing source data."
              : `${String(seasons.length)} season${seasons.length === 1 ? "" : "s"} attached`}
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:items-end">
          {seasons.length > 0 ? (
            <label className="space-y-1 text-xs font-medium text-muted-foreground">
              Active season
              <select
                className="block h-9 min-w-48 rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={selectedSeasonId}
                onChange={(event) => {
                  selectSeason(event.target.value);
                }}
              >
                {seasons.map(({ season, summary }) => (
                  <option key={season.id} value={season.id}>
                    {season.season_year}
                    {summary.league_name ? ` · ${summary.league_name}` : ""}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {selectedSeasonId && selectedSeason ? (
              <RefreshSheet
                competitionId={competition.id}
                seasonId={selectedSeasonId}
                seasonYear={selectedSeason.season.season_year}
                leagueName={selectedSeason.summary.league_name}
                disabled={archived}
                onOutcome={(outcome) => {
                  setLatestOutcome({ seasonId: selectedSeasonId, outcome });
                }}
              />
            ) : null}
            <AddSeasonDialog
              competitionId={competition.id}
              disabled={archived}
              onCreated={selectSeason}
            />
          </div>
        </div>
      </header>

      {archived ? (
        <p className="mt-6 rounded-md border border-border bg-muted/60 p-4 text-sm text-muted-foreground">
          This archived competition is available for historical inspection. New
          seasons and refresh operations are disabled.
        </p>
      ) : null}

      {seasons.length === 0 ? (
        <section className="mt-10 rounded-lg border border-dashed border-border bg-card/60 p-8 text-center sm:p-12">
          <div className="mx-auto flex size-12 items-center justify-center rounded-full border border-border bg-background">
            <Trophy
              className="size-5 text-muted-foreground"
              aria-hidden="true"
            />
          </div>
          <h2 className="mt-5 font-editorial text-2xl font-semibold">
            Add the first season
          </h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
            Enter the season year and the Sleeper league ID assigned for that
            year. Sequence is derived automatically.
          </p>
          {!archived ? (
            <div className="mt-6 flex justify-center">
              <AddSeasonDialog
                competitionId={competition.id}
                prominent
                onCreated={selectSeason}
              />
            </div>
          ) : null}
        </section>
      ) : (
        <>
          <section className="mt-10" aria-labelledby="seasons-heading">
            <div className="mb-4 flex items-center justify-between">
              <h2
                id="seasons-heading"
                className="font-editorial text-2xl font-semibold"
              >
                Seasons
              </h2>
              {seasonsQuery.isFetching ? (
                <span className="text-xs text-muted-foreground" role="status">
                  Updating…
                </span>
              ) : null}
            </div>
            <SeasonTable
              items={seasons}
              selectedSeasonId={selectedSeasonId}
              onSelect={selectSeason}
            />
            <SeasonCards
              items={seasons}
              selectedSeasonId={selectedSeasonId}
              onSelect={selectSeason}
            />
          </section>

          <section className="mt-10" aria-labelledby="selected-season-heading">
            <div className="mb-4 flex items-center gap-3">
              <Database
                className="size-5 text-muted-foreground"
                aria-hidden="true"
              />
              <h2
                id="selected-season-heading"
                className="font-editorial text-2xl font-semibold"
              >
                {selectedSeason?.season.season_year} data status
              </h2>
            </div>
            {seasonDetailQuery.isPending ? (
              <Skeleton className="h-56 w-full rounded-lg" />
            ) : seasonDetailQuery.isError ? (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
                <p className="text-sm text-destructive">
                  {seasonDetailQuery.error instanceof ApiError
                    ? seasonDetailQuery.error.message
                    : "The selected season could not be loaded."}
                </p>
                <Button
                  className="mt-4"
                  variant="outline"
                  onClick={() => void seasonDetailQuery.refetch()}
                >
                  Try again
                </Button>
              </div>
            ) : detail && selectedSeasonId && selectedSeason ? (
              <>
                <div className="grid gap-5 lg:grid-cols-[1.2fr_1fr]">
                  <article className="rounded-lg border border-border bg-card p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                          Sleeper league
                        </p>
                        <h3 className="mt-2 font-editorial text-2xl font-semibold">
                          {detail.normalized_overview?.league_name ??
                            "Awaiting first refresh"}
                        </h3>
                        <p className="mt-2 break-all text-sm text-muted-foreground">
                          ID {detail.season.sleeper_league_id}
                        </p>
                      </div>
                      {detail.normalized_overview?.status ? (
                        <Badge variant="outline">
                          {detail.normalized_overview.status}
                        </Badge>
                      ) : null}
                    </div>
                    {detail.normalized_overview ? (
                      <dl className="mt-6 grid grid-cols-2 gap-5 border-t border-border pt-5 text-sm sm:grid-cols-4">
                        <div>
                          <dt className="text-xs text-muted-foreground">
                            Rosters
                          </dt>
                          <dd className="mt-1 font-medium">
                            {detail.normalized_overview.roster_count}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs text-muted-foreground">
                            Playoff start
                          </dt>
                          <dd className="mt-1 font-medium">
                            {detail.normalized_overview.playoff_start_week ??
                              "—"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs text-muted-foreground">
                            Playoff teams
                          </dt>
                          <dd className="mt-1 font-medium">
                            {detail.normalized_overview.playoff_team_count ??
                              "—"}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-xs text-muted-foreground">
                            League average match
                          </dt>
                          <dd className="mt-1 font-medium">
                            {detail.normalized_overview.league_average_match ??
                              "—"}
                          </dd>
                        </div>
                      </dl>
                    ) : (
                      <p className="mt-6 border-t border-border pt-5 text-sm leading-6 text-muted-foreground">
                        No normalized Sleeper observations exist yet. A manual
                        refresh will load league settings, rosters, and the
                        selected week boundary.
                      </p>
                    )}
                  </article>

                  <article className="rounded-lg border border-border bg-card p-5">
                    <div className="flex items-center gap-2">
                      <RefreshCw
                        className="size-4 text-muted-foreground"
                        aria-hidden="true"
                      />
                      <h3 className="font-semibold">Freshness</h3>
                    </div>
                    <dl className="mt-5 space-y-4 text-sm">
                      <div className="flex items-start justify-between gap-4">
                        <dt className="text-muted-foreground">
                          Last refreshed
                        </dt>
                        <dd className="text-right">
                          <DateTime
                            value={
                              detail.summary.latest_terminal_refresh
                                ?.completed_at ?? null
                            }
                            showExact
                          />
                        </dd>
                      </div>
                      <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
                        <dt className="text-muted-foreground">
                          Last successful refresh
                        </dt>
                        <dd className="text-right">
                          <DateTime
                            value={detail.summary.latest_successful_refresh_at}
                            showExact
                          />
                        </dd>
                      </div>
                      <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
                        <dt className="text-muted-foreground">
                          Latest generation snapshot
                        </dt>
                        <dd className="text-right">
                          <DateTime
                            value={detail.summary.latest_ready_snapshot_at}
                            empty="None built"
                            showExact
                          />
                        </dd>
                      </div>
                    </dl>
                    <p className="mt-5 border-t border-border pt-4 text-xs leading-5 text-muted-foreground">
                      Snapshot time records when frozen generation input was
                      built or reused. It is not Sleeper freshness.
                    </p>
                  </article>
                </div>
                <RosterMappingPanel
                  competitionId={competition.id}
                  seasonId={selectedSeasonId}
                  seasonYear={selectedSeason.season.season_year}
                  requestedThroughWeek={
                    detail.summary.latest_terminal_refresh
                      ?.requested_through_week
                  }
                  disabled={archived}
                  onOutcome={(outcome) => {
                    setLatestOutcome({ seasonId: selectedSeasonId, outcome });
                  }}
                />
              </>
            ) : null}
          </section>

          {latestOutcome && latestOutcome.seasonId === selectedSeasonId ? (
            <RefreshOutcomePanel outcome={latestOutcome.outcome} />
          ) : null}

          {selectedSeasonId ? (
            <section
              className="mt-10"
              aria-labelledby="refresh-history-heading"
            >
              <h2
                id="refresh-history-heading"
                className="font-editorial text-2xl font-semibold"
              >
                Refresh history
              </h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Newest-first source refreshes for the selected season. Stored
                history preserves terminal status and aggregate request audit.
              </p>
              <div className="mt-5">
                <RefreshHistory
                  competitionId={competition.id}
                  seasonId={selectedSeasonId}
                  page={refreshPage}
                  onPageChange={setRefreshPage}
                />
              </div>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
