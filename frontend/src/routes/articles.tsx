import {
  ArrowLeft,
  ArrowRight,
  CircleAlert,
  Library,
  PlusCircle,
} from "lucide-react";
import { useEffect } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { ApiError } from "@/api/errors";
import { DateTime } from "@/components/shared/date-time";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ArticleSummary, GenerationKind } from "@/features/articles/api";
import { useArticleList } from "@/features/articles/queries";
import { useSeasonList } from "@/features/seasons/queries";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 25;
const seasonListParameters = { limit: 200, offset: 0 } as const;

function positivePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function generationKind(value: string | null): GenerationKind | undefined {
  return value === "live" || value === "backtest" ? value : undefined;
}

function titleCase(value: string): string {
  return value
    .split(/[_\-.\s]+/u)
    .filter(Boolean)
    .map((part) => `${part[0]?.toUpperCase() ?? ""}${part.slice(1)}`)
    .join(" ");
}

function weekLabel(article: ArticleSummary): string {
  if (article.week_start === null || article.week_end === null)
    return "Weeks —";
  return article.week_start === article.week_end
    ? `Week ${String(article.week_start)}`
    : `Weeks ${String(article.week_start)}–${String(article.week_end)}`;
}

function formatCost(value: string | null, currency: string): string {
  if (value === null) return "Unavailable";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return `${currency} ${value}`;
  if (amount > 0 && amount < 0.000001) return `${currency} ${value}`;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: amount < 0.01 ? 6 : 2,
    }).format(amount);
  } catch {
    return `${currency} ${value}`;
  }
}

function actualModelLabel(article: ArticleSummary): string {
  const models = article.usage.models;
  if (models.length === 0) return "No recorded model";
  const first = models[0];
  const identity = [first?.provider, first?.model].filter(Boolean).join(" / ");
  return models.length > 1
    ? `${identity || "Unknown model"} +${String(models.length - 1)}`
    : identity || "Unknown model";
}

function estimatedCostLabel(article: ArticleSummary): string {
  if (article.usage.estimated_cost === null) return "Estimate unavailable";
  return `${formatCost(
    article.usage.estimated_cost,
    article.usage.currency,
  )} estimated`;
}

function tokenLabel(article: ArticleSummary): string {
  if (article.usage.complete) {
    return `${article.usage.total_tokens.toLocaleString()} tokens`;
  }
  if (article.usage.attempt_count === 0) return "Usage unavailable";
  return `${article.usage.total_tokens.toLocaleString()} recorded tokens`;
}

function relationshipLabel(article: ArticleSummary): string | undefined {
  if (article.rerun_of_generation_id) {
    return `Exact rerun of ${article.rerun_of_generation_id.slice(0, 8)}`;
  }
  if (article.workspace_sequence_number !== null) {
    return `Workspace run ${String(article.workspace_sequence_number)}`;
  }
  return undefined;
}

function ArticleTable({
  competitionId,
  items,
}: {
  competitionId: string;
  items: ArticleSummary[];
}): React.JSX.Element {
  return (
    <div className="hidden overflow-hidden rounded-lg border border-border bg-card lg:block">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-muted/70 text-xs uppercase tracking-[0.1em] text-muted-foreground">
          <tr>
            <th className="px-5 py-3 font-semibold">Article</th>
            <th className="px-4 py-3 font-semibold">Scope</th>
            <th className="px-4 py-3 font-semibold">Models</th>
            <th className="px-4 py-3 font-semibold">Usage</th>
            <th className="px-4 py-3 font-semibold">Completed</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((article) => (
            <tr
              key={article.generation_id}
              className="align-top hover:bg-muted/35"
            >
              <td className="max-w-md px-5 py-4">
                <Link
                  className="font-editorial text-lg font-semibold underline-offset-4 hover:underline"
                  to={`/competitions/${competitionId}/generations/${article.generation_id}?tab=article`}
                >
                  {article.title}
                </Link>
                <p
                  className="mt-1 max-w-md truncate text-xs text-muted-foreground"
                  title={article.request_text}
                >
                  {article.request_text}
                </p>
                {article.rerun_of_generation_id ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Exact rerun · source{" "}
                    <Link
                      className="font-mono text-primary underline-offset-4 hover:underline"
                      to={`/competitions/${competitionId}/generations/${article.rerun_of_generation_id}`}
                    >
                      {article.rerun_of_generation_id.slice(0, 8)}
                    </Link>
                  </p>
                ) : article.workspace_sequence_number !== null ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Workspace run {article.workspace_sequence_number}
                  </p>
                ) : null}
              </td>
              <td className="px-4 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{article.season_year}</span>
                  <Badge variant="outline">{titleCase(article.kind)}</Badge>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {weekLabel(article)}
                </p>
              </td>
              <td className="max-w-56 px-4 py-4">
                <p className="break-all font-medium">
                  {article.requested_primary_model}
                </p>
                <p className="mt-1 break-all text-xs text-muted-foreground">
                  Actual: {actualModelLabel(article)}
                </p>
              </td>
              <td className="px-4 py-4">
                <p className="font-medium">{tokenLabel(article)}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {estimatedCostLabel(article)}
                </p>
                {!article.usage.complete ? (
                  <Badge className="mt-2" variant="secondary">
                    Incomplete usage/cost
                  </Badge>
                ) : null}
              </td>
              <td className="px-4 py-4">
                <DateTime value={article.completed_at} showExact />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ArticleCards({
  competitionId,
  items,
}: {
  competitionId: string;
  items: ArticleSummary[];
}): React.JSX.Element {
  return (
    <div className="space-y-3 lg:hidden">
      {items.map((article) => (
        <article
          key={article.generation_id}
          className="rounded-lg border border-border bg-card p-5"
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{titleCase(article.kind)}</Badge>
            <span className="text-xs text-muted-foreground">
              {article.season_year} · {weekLabel(article)}
            </span>
          </div>
          <h2 className="mt-3 font-editorial text-2xl font-semibold leading-tight">
            <Link
              className="underline-offset-4 hover:underline"
              to={`/competitions/${competitionId}/generations/${article.generation_id}?tab=article`}
            >
              {article.title}
            </Link>
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {article.request_text}
          </p>
          {relationshipLabel(article) ? (
            <p className="mt-2 text-xs text-muted-foreground">
              {relationshipLabel(article)}
            </p>
          ) : null}
          <dl className="mt-5 grid gap-4 border-t border-border pt-4 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-xs text-muted-foreground">Models</dt>
              <dd className="mt-1 break-all font-medium">
                {article.requested_primary_model}
              </dd>
              <dd className="mt-1 break-all text-xs text-muted-foreground">
                Actual: {actualModelLabel(article)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Usage</dt>
              <dd className="mt-1 font-medium">{tokenLabel(article)}</dd>
              <dd className="mt-1 text-xs text-muted-foreground">
                {estimatedCostLabel(article)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Completed</dt>
              <dd className="mt-1">
                <DateTime value={article.completed_at} showExact />
              </dd>
            </div>
          </dl>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            {!article.usage.complete ? (
              <Badge variant="secondary">Incomplete usage/cost</Badge>
            ) : (
              <span />
            )}
            <Link
              className={buttonVariants({ variant: "outline", size: "sm" })}
              to={`/competitions/${competitionId}/generations/${article.generation_id}?tab=article`}
            >
              Read article
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </div>
        </article>
      ))}
    </div>
  );
}

function ArticleListSkeleton(): React.JSX.Element {
  return (
    <div className="space-y-3" aria-label="Loading submitted articles">
      {[0, 1, 2].map((item) => (
        <Skeleton key={item} className="h-32 w-full rounded-lg" />
      ))}
    </div>
  );
}

export function Component(): React.JSX.Element {
  const { competitionId } = useParams();
  const [searchParameters, setSearchParameters] = useSearchParams();
  const page = positivePage(searchParameters.get("page"));
  const seasonId = searchParameters.get("season") ?? undefined;
  const kind = generationKind(searchParameters.get("kind"));
  const seasonsQuery = useSeasonList(competitionId, seasonListParameters);
  const articlesQuery = useArticleList(competitionId, {
    competitionSeasonId: seasonId,
    kind,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const totalPages = Math.max(
    1,
    Math.ceil((articlesQuery.data?.page.total ?? 0) / PAGE_SIZE),
  );

  useEffect(() => {
    if (articlesQuery.data && page > totalPages) {
      const next = new URLSearchParams(searchParameters);
      if (totalPages === 1) next.delete("page");
      else next.set("page", String(totalPages));
      setSearchParameters(next, { replace: true });
    }
  }, [
    articlesQuery.data,
    page,
    searchParameters,
    setSearchParameters,
    totalPages,
  ]);

  function setFilter(name: "season" | "kind", value: string): void {
    const next = new URLSearchParams(searchParameters);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete("page");
    setSearchParameters(next);
  }

  function setPage(nextPage: number): void {
    const next = new URLSearchParams(searchParameters);
    if (nextPage === 1) next.delete("page");
    else next.set("page", String(nextPage));
    setSearchParameters(next);
  }

  function clearFilters(): void {
    setSearchParameters({});
  }

  if (!competitionId) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
        <h1 className="font-editorial text-3xl font-semibold">
          League scope unavailable
        </h1>
      </div>
    );
  }

  const items = articlesQuery.data?.page.items ?? [];
  const filtered = seasonId !== undefined || kind !== undefined;
  const error = articlesQuery.error;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <header className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            Submitted work
          </p>
          <h1 className="mt-3 font-editorial text-4xl font-semibold tracking-tight sm:text-5xl">
            Articles
          </h1>
          <p className="mt-4 text-base leading-7 text-muted-foreground">
            Browse exact submitted article versions and open the durable run
            record behind each one.
          </p>
        </div>
        <Link
          className={buttonVariants({ variant: "default" })}
          to={`/competitions/${competitionId}/generate`}
        >
          <PlusCircle className="size-4" aria-hidden="true" />
          Generate article
        </Link>
      </header>

      <section className="mt-9 rounded-lg border border-border bg-card p-4 sm:p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
            Season
            <select
              className="block h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={seasonId ?? ""}
              onChange={(event) => {
                setFilter("season", event.target.value);
              }}
            >
              <option value="">All seasons</option>
              {(seasonsQuery.data?.page.items ?? []).map(
                ({ season, summary }) => (
                  <option key={season.id} value={season.id}>
                    {season.season_year}
                    {summary.league_name ? ` · ${summary.league_name}` : ""}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
            Mode
            <select
              className="block h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={kind ?? ""}
              onChange={(event) => {
                setFilter("kind", event.target.value);
              }}
            >
              <option value="">Live and backtests</option>
              <option value="live">Live</option>
              <option value="backtest">Historical backtest</option>
            </select>
          </label>
        </div>
      </section>

      <section className="mt-8" aria-labelledby="article-list-heading">
        <div className="mb-4 flex min-h-6 items-center justify-between gap-3">
          <h2
            id="article-list-heading"
            className="font-editorial text-2xl font-semibold"
          >
            Submitted articles
          </h2>
          {articlesQuery.isFetching && !articlesQuery.isPending ? (
            <span className="text-xs text-muted-foreground" role="status">
              Updating…
            </span>
          ) : null}
        </div>

        {articlesQuery.isPending ? <ArticleListSkeleton /> : null}

        {error ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
            <CircleAlert
              className="size-6 text-destructive"
              aria-hidden="true"
            />
            <h3 className="mt-3 font-semibold">Article library unavailable</h3>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {error instanceof ApiError
                ? error.message
                : "Submitted article history could not be loaded."}
            </p>
            <Button
              className="mt-4"
              variant="outline"
              onClick={() => {
                void articlesQuery.refetch();
              }}
            >
              Try again
            </Button>
          </div>
        ) : null}

        {articlesQuery.isSuccess && items.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-card/60 p-8 text-center sm:p-12">
            <Library
              className="mx-auto size-8 text-muted-foreground"
              aria-hidden="true"
            />
            <h3 className="mt-5 font-editorial text-2xl font-semibold">
              {filtered
                ? "No articles match these filters"
                : "No submitted articles yet"}
            </h3>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
              {filtered
                ? "Choose another season or mode to broaden the article history."
                : "Successful generations with an explicit submitted version will appear here."}
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              {filtered ? (
                <Button variant="outline" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : null}
              <Link
                className={buttonVariants({ variant: "default" })}
                to={`/competitions/${competitionId}/generate`}
              >
                Generate article
              </Link>
            </div>
          </div>
        ) : null}

        {articlesQuery.isSuccess && items.length > 0 ? (
          <>
            <ArticleTable competitionId={competitionId} items={items} />
            <ArticleCards competitionId={competitionId} items={items} />
            {articlesQuery.data.page.total > PAGE_SIZE ? (
              <div className="mt-5 flex flex-col gap-3 text-sm sm:flex-row sm:items-center sm:justify-between">
                <span className="text-muted-foreground">
                  Page {page} of {totalPages} · {articlesQuery.data.page.total}{" "}
                  articles
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
                    <ArrowLeft className="size-4" aria-hidden="true" />
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => {
                      setPage(page + 1);
                    }}
                  >
                    Next
                    <ArrowRight className="size-4" aria-hidden="true" />
                  </Button>
                </div>
              </div>
            ) : null}
          </>
        ) : null}
      </section>

      <div className="mt-8">
        <Link
          className={cn(buttonVariants({ variant: "ghost" }), "px-0")}
          to={`/competitions/${competitionId}`}
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to league overview
        </Link>
      </div>
    </div>
  );
}
