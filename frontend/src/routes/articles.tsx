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
import type { ArticleSummary } from "@/features/articles/api";
import {
  ARTICLE_PAGE_SIZE,
  articleKind,
  articleReaderPath,
  positiveArticlePage,
} from "@/features/articles/navigation";
import { useArticleList } from "@/features/articles/queries";
import { useSeasonList } from "@/features/seasons/queries";
import { cn } from "@/lib/utils";

const seasonListParameters = { limit: 200, offset: 0 } as const;

function weekLabel(article: ArticleSummary): string {
  if (article.week_start === null || article.week_end === null)
    return "Weeks not recorded";
  return article.week_start === article.week_end
    ? `Week ${String(article.week_start)}`
    : `Weeks ${String(article.week_start)}–${String(article.week_end)}`;
}

function ArticleContext({
  article,
}: {
  article: ArticleSummary;
}): React.JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <Badge variant={article.kind === "backtest" ? "secondary" : "outline"}>
        {article.kind === "backtest" ? "Historical backtest" : "Live"}
      </Badge>
      <span>{article.season_year}</span>
      <span aria-hidden="true">·</span>
      <span>{weekLabel(article)}</span>
      <span aria-hidden="true">·</span>
      <DateTime value={article.completed_at} />
    </div>
  );
}
function AssignmentFallback({
  article,
  featured = false,
}: {
  article: ArticleSummary;
  featured?: boolean;
}): React.JSX.Element {
  return (
    <div className={featured ? "mt-6 max-w-2xl" : "mt-3 max-w-3xl"}>
      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        Assignment
      </p>
      <p
        className={cn(
          "mt-1 text-muted-foreground",
          featured ? "text-base leading-7" : "line-clamp-2 text-sm leading-6",
        )}
      >
        {article.request_text}
      </p>
    </div>
  );
}

function FeaturedArticle({
  article,
  competitionId,
  searchParameters,
}: {
  article: ArticleSummary;
  competitionId: string;
  searchParameters: URLSearchParams;
}): React.JSX.Element {
  return (
    <article className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="border-b border-border bg-muted/40 px-5 py-3 sm:px-8">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Latest article
        </p>
      </div>
      <div className="px-5 py-7 sm:px-8 sm:py-10">
        <ArticleContext article={article} />
        <h2 className="mt-5 max-w-4xl font-editorial text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
          <Link
            className="underline-offset-4 hover:underline"
            to={articleReaderPath(
              competitionId,
              article.generation_id,
              searchParameters,
            )}
          >
            {article.title}
          </Link>
        </h2>
        <AssignmentFallback article={article} featured />
        <div className="mt-7">
          <Link
            className={buttonVariants({ variant: "default" })}
            to={articleReaderPath(
              competitionId,
              article.generation_id,
              searchParameters,
            )}
          >
            Read article
            <ArrowRight className="size-4" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </article>
  );
}

function ArticleArchive({
  competitionId,
  items,
  searchParameters,
}: {
  competitionId: string;
  items: ArticleSummary[];
  searchParameters: URLSearchParams;
}): React.JSX.Element | null {
  if (items.length === 0) return null;

  return (
    <section className="mt-10" aria-labelledby="article-archive-heading">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Archive
          </p>
          <h2
            id="article-archive-heading"
            className="mt-2 font-editorial text-3xl font-semibold"
          >
            More articles
          </h2>
        </div>
      </div>
      <div className="divide-y divide-border border-y border-border">
        {items.map((article) => (
          <article
            key={article.generation_id}
            className="grid gap-5 py-6 md:grid-cols-[minmax(0,1fr)_auto] md:items-center"
          >
            <div className="min-w-0">
              <ArticleContext article={article} />
              <h3 className="mt-3 max-w-4xl font-editorial text-2xl font-semibold leading-snug sm:text-3xl">
                <Link
                  className="underline-offset-4 hover:underline"
                  to={articleReaderPath(
                    competitionId,
                    article.generation_id,
                    searchParameters,
                  )}
                >
                  {article.title}
                </Link>
              </h3>
              <AssignmentFallback article={article} />
            </div>
            <Link
              className={buttonVariants({ variant: "outline", size: "sm" })}
              to={articleReaderPath(
                competitionId,
                article.generation_id,
                searchParameters,
              )}
            >
              Read
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </article>
        ))}
      </div>
    </section>
  );
}

function ArticleListSkeleton(): React.JSX.Element {
  return (
    <div className="space-y-6" aria-label="Loading submitted articles">
      <Skeleton className="h-80 w-full rounded-xl" />
      {[0, 1, 2].map((item) => (
        <Skeleton key={item} className="h-36 w-full rounded-lg" />
      ))}
    </div>
  );
}

export function Component(): React.JSX.Element {
  const { competitionId } = useParams();
  const [searchParameters, setSearchParameters] = useSearchParams();
  const page = positiveArticlePage(searchParameters.get("page"));
  const seasonId = searchParameters.get("season") ?? undefined;
  const kind = articleKind(searchParameters.get("kind"));
  const seasonsQuery = useSeasonList(competitionId, seasonListParameters);
  const articlesQuery = useArticleList(competitionId, {
    competitionSeasonId: seasonId,
    kind,
    limit: ARTICLE_PAGE_SIZE,
    offset: (page - 1) * ARTICLE_PAGE_SIZE,
  });
  const totalPages = Math.max(
    1,
    Math.ceil((articlesQuery.data?.page.total ?? 0) / ARTICLE_PAGE_SIZE),
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
  const featuredArticle = page === 1 ? items[0] : undefined;
  const archiveItems = featuredArticle ? items.slice(1) : items;
  const filtered = seasonId !== undefined || kind !== undefined;
  const error = articlesQuery.error;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <header className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
            League desk
          </p>
          <h1 className="mt-3 font-editorial text-4xl font-semibold tracking-tight sm:text-5xl">
            Articles
          </h1>
          <p className="mt-4 text-base leading-7 text-muted-foreground">
            Read the latest submitted coverage or browse the league archive.
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

      <section
        className="mt-8 rounded-lg border border-border bg-card p-4"
        aria-label="Article filters"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-1.5 text-xs font-medium text-muted-foreground">
            Season
            <select
              className="block h-9 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={seasonId ?? ""}
              onChange={(event) => setFilter("season", event.target.value)}
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
              onChange={(event) => setFilter("kind", event.target.value)}
            >
              <option value="">Live and backtests</option>
              <option value="live">Live</option>
              <option value="backtest">Historical backtest</option>
            </select>
          </label>
        </div>
      </section>

      <section className="mt-8" aria-label="Submitted articles">
        {articlesQuery.isFetching && !articlesQuery.isPending ? (
          <p
            className="mb-3 text-right text-xs text-muted-foreground"
            role="status"
          >
            Updating articles…
          </p>
        ) : null}

        {articlesQuery.isPending ? <ArticleListSkeleton /> : null}

        {error ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
            <CircleAlert className="size-6 text-destructive" aria-hidden="true" />
            <h2 className="mt-3 font-semibold">Article library unavailable</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {error instanceof ApiError
                ? error.message
                : "Submitted article history could not be loaded."}
            </p>
            <Button
              className="mt-4"
              variant="outline"
              onClick={() => void articlesQuery.refetch()}
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
            <h2 className="mt-5 font-editorial text-2xl font-semibold">
              {filtered
                ? "No articles match these filters"
                : "No submitted articles yet"}
            </h2>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
              {filtered
                ? "Choose another season or mode to broaden the article archive."
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

        {articlesQuery.isSuccess && featuredArticle ? (
          <FeaturedArticle
            article={featuredArticle}
            competitionId={competitionId}
            searchParameters={searchParameters}
          />
        ) : null}

        {articlesQuery.isSuccess ? (
          <ArticleArchive
            competitionId={competitionId}
            items={archiveItems}
            searchParameters={searchParameters}
          />
        ) : null}

        {articlesQuery.isSuccess &&
        articlesQuery.data.page.total > ARTICLE_PAGE_SIZE ? (
          <div className="mt-7 flex flex-col gap-3 text-sm sm:flex-row sm:items-center sm:justify-between">
            <span className="text-muted-foreground">
              Page {page} of {totalPages} · {articlesQuery.data.page.total}{" "}
              articles
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                <ArrowLeft className="size-4" aria-hidden="true" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
              >
                Next
                <ArrowRight className="size-4" aria-hidden="true" />
              </Button>
            </div>
          </div>
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
