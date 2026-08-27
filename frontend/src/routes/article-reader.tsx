import {
  ArrowLeft,
  ArrowRight,
  Check,
  CircleAlert,
  Copy,
  FileSearch,
  LoaderCircle,
  Pencil,
  RotateCcw,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import { ApiError } from "@/api/errors";
import { DateTime } from "@/components/shared/date-time";
import { MarkdownArticle } from "@/components/shared/markdown-article";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { SubmittedArticleResponse } from "@/features/articles/api";
import {
  ARTICLE_PAGE_SIZE,
  articleKind,
  articleLibraryPath,
  positiveArticlePage,
  siblingArticlePath,
} from "@/features/articles/navigation";
import {
  useArticleList,
  useSubmittedArticle,
} from "@/features/articles/queries";
import { ArtifactBrowser } from "@/features/artifacts/artifact-browser";
import { ExecutionTimeline } from "@/features/execution/execution-timeline";
import {
  createGenerationFormValuesFromDetail,
  saveGenerationDraft,
} from "@/features/generations/draft";
import { useRerunGeneration } from "@/features/generations/queries";
import { useSeasonList } from "@/features/seasons/queries";
import { UsagePanel } from "@/features/usage/usage-panel";
import { cn } from "@/lib/utils";

const seasonListParameters = { limit: 200, offset: 0 } as const;
const detailTabs = ["overview", "artifacts", "execution", "usage"] as const;
type DetailTab = (typeof detailTabs)[number];
type SubmittedGeneration = SubmittedArticleResponse["generation"];
type SubmittedArtifact = SubmittedArticleResponse["artifact"];
type SubmittedVersion = SubmittedArticleResponse["version"];

interface SplitArticle {
  body: string;
  title: string;
}

function titleCase(value: string): string {
  return value
    .split(/[_\-.\s]+/u)
    .filter(Boolean)
    .map((part) => `${part[0]?.toUpperCase() ?? ""}${part.slice(1)}`)
    .join(" ");
}

function weekLabel(start: number | null, end: number | null): string {
  if (start === null || end === null) return "Weeks not recorded";
  return start === end
    ? `Week ${String(start)}`
    : `Weeks ${String(start)}–${String(end)}`;
}

function plainHeading(markdown: string): string {
  return markdown
    .replace(/\[([^\]]+)\]\([^)]+\)/gu, "$1")
    .replace(/`([^`]+)`/gu, "$1")
    .replace(/<[^>]*>/gu, "")
    .replace(/(?<!\\)[*_~]/gu, "")
    .replace(/\\([\\`*{}[\]()#+.!_>~-])/gu, "$1")
    .replaceAll("&amp;", "&")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .trim();
}

function splitArticle(markdown: string): SplitArticle {
  const lines = markdown.split(/\r?\n/u);
  let fenceCharacter: string | undefined;
  let fenceLength = 0;

  for (const [index, line] of lines.entries()) {
    const fence = /^\s*(`{3,}|~{3,})/u.exec(line);
    if (fenceCharacter) {
      const marker = fence?.[1];
      const fenceText = fence?.[0];
      if (
        marker?.[0] === fenceCharacter &&
        marker.length >= fenceLength &&
        fenceText !== undefined &&
        /^\s*$/.test(line.slice(fenceText.length))
      ) {
        fenceCharacter = undefined;
        fenceLength = 0;
      }
      continue;
    }
    if (fence?.[1]) {
      fenceCharacter = fence[1][0];
      fenceLength = fence[1].length;
      continue;
    }

    const heading = /^\s{0,3}#(?!#)\s+(.+?)\s*#*\s*$/u.exec(line);
    if (!heading?.[1]) continue;
    const title = plainHeading(heading[1]);
    if (!title) continue;
    lines.splice(index, 1);
    return { title, body: lines.join("\n").trimStart() };
  }

  return { title: "Untitled article", body: markdown };
}

function ReaderSkeleton(): React.JSX.Element {
  return (
    <div className="mx-auto max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
      <Skeleton className="h-8 w-36" />
      <div className="mx-auto mt-12 max-w-3xl space-y-5">
        <Skeleton className="h-5 w-64" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-5 w-80" />
        <Skeleton className="mt-12 h-[32rem] w-full" />
      </div>
    </div>
  );
}
function RunOverview({
  artifact,
  competitionId,
  generation,
  seasonYear,
  version,
}: {
  artifact: SubmittedArtifact;
  competitionId: string;
  generation: SubmittedGeneration;
  seasonYear?: number;
  version: SubmittedVersion;
}): React.JSX.Element {
  const navigate = useNavigate();
  const editableValues = createGenerationFormValuesFromDetail(generation);
  const fallbackModels = editableValues?.model.fallbackModels ?? [];
  const rerun = useRerunGeneration(competitionId, generation.id);

  async function rerunGeneration(): Promise<void> {
    try {
      const response = await rerun.mutateAsync();
      toast.success("Rerun queued");
      await navigate(
        `/competitions/${competitionId}/generations/${response.generation.id}`,
      );
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : "The rerun could not be queued.",
      );
    }
  }

  function editSettings(): void {
    if (!editableValues) return;
    saveGenerationDraft(competitionId, editableValues);
    void navigate(
      `/competitions/${competitionId}/generate?season=${generation.competition_season_id}`,
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-border bg-card p-5 sm:p-6">
        <h3 className="font-editorial text-2xl font-semibold">Assignment</h3>
        <p className="mt-4 whitespace-pre-wrap text-sm leading-7">
          {generation.request_text}
        </p>
        <div className="mt-6 flex flex-wrap gap-2 border-t border-border pt-5">
          <Button
            variant="outline"
            disabled={rerun.isPending}
            onClick={() => void rerunGeneration()}
          >
            {rerun.isPending ? (
              <LoaderCircle
                className="size-4 animate-spin"
                aria-hidden="true"
              />
            ) : (
              <RotateCcw className="size-4" aria-hidden="true" />
            )}
            Rerun exact request
          </Button>
          <Button
            variant="outline"
            disabled={!editableValues}
            onClick={editSettings}
          >
            <Pencil className="size-4" aria-hidden="true" />
            Edit settings
          </Button>
          <Link
            className={buttonVariants({ variant: "ghost" })}
            to={`/competitions/${competitionId}/generations/${generation.id}?tab=execution`}
          >
            Open generation record
          </Link>
        </div>
        {rerun.isError ? (
          <div
            className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
            role="alert"
          >
            {rerun.error instanceof ApiError
              ? rerun.error.message
              : "The rerun could not be queued."}
          </div>
        ) : null}
      </section>

      <section className="rounded-lg border border-border bg-card p-5 sm:p-6">
        <h3 className="font-editorial text-2xl font-semibold">Run details</h3>
        <dl className="mt-5 grid gap-5 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted-foreground">Season and scope</dt>
            <dd className="mt-1 font-medium">
              {seasonYear ?? generation.competition_season_id} ·{" "}
              {weekLabel(generation.week_start, generation.week_end)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Mode</dt>
            <dd className="mt-1 font-medium">{titleCase(generation.kind)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Completed</dt>
            <dd className="mt-1">
              <DateTime value={generation.completed_at} showExact />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Model chain</dt>
            <dd className="mt-1 break-all font-medium">
              {generation.requested_primary_model}
              {fallbackModels.length > 0
                ? ` → ${fallbackModels.join(" → ")}`
                : ""}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Submitted version</dt>
            <dd className="mt-1 break-all font-mono text-xs">
              Revision {version.revision_number} · {artifact.path}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Snapshot</dt>
            <dd className="mt-1 break-all font-mono text-xs">
              {generation.data_snapshot_id ?? "Not recorded"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Memory input</dt>
            <dd className="mt-1 break-all font-mono text-xs">
              {generation.input_memory_revision_id ??
                generation.input_memory_artifact_version_id ??
                "No persisted memory input"}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Manifest hash</dt>
            <dd className="mt-1 break-all font-mono text-xs">
              {generation.manifest_hash ?? "Not recorded"}
            </dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-xs text-muted-foreground">Content hash</dt>
            <dd className="mt-1 break-all font-mono text-xs">
              {version.content_hash}
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}

function RunDetailsSheet({
  article,
  competitionId,
  seasonYear,
}: {
  article: SubmittedArticleResponse;
  competitionId: string;
  seasonYear?: number;
}): React.JSX.Element {
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const split = useMemo(
    () => splitArticle(article.version.content),
    [article.version.content],
  );

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline">
          <FileSearch className="size-4" aria-hidden="true" />
          Behind this article
        </Button>
      </SheetTrigger>
      <SheetContent
        side="right"
        className="w-full max-w-5xl overflow-hidden p-0 sm:w-[min(64rem,94vw)]"
      >
        <SheetHeader className="mb-0 border-b border-border px-5 py-5 pr-12 sm:px-7">
          <SheetTitle>Behind “{split.title}”</SheetTitle>
          <SheetDescription>
            Assignment, provenance, artifacts, execution, and usage for this
            exact submitted version.
          </SheetDescription>
        </SheetHeader>
        <Tabs
          className="min-h-0 flex-1 gap-0"
          value={activeTab}
          onValueChange={(value) => {
            setActiveTab(value as DetailTab);
          }}
        >
          <div className="shrink-0 overflow-x-auto border-b border-border px-5 sm:px-7">
            <TabsList className="min-w-max border-b-0">
              {detailTabs.map((tab) => (
                <TabsTrigger key={tab} value={tab}>
                  {titleCase(tab)}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-6 sm:px-7">
            <TabsContent value="overview">
              <RunOverview
                artifact={article.artifact}
                competitionId={competitionId}
                generation={article.generation}
                seasonYear={seasonYear}
                version={article.version}
              />
            </TabsContent>
            <TabsContent value="artifacts">
              <ArtifactBrowser
                competitionId={competitionId}
                generationId={article.generation.id}
                submittedVersionId={article.version.id}
                active={activeTab === "artifacts"}
              />
            </TabsContent>
            <TabsContent value="execution">
              <ExecutionTimeline
                competitionId={competitionId}
                generationId={article.generation.id}
                active={activeTab === "execution"}
                generationActive={false}
              />
            </TabsContent>
            <TabsContent value="usage">
              <UsagePanel
                competitionId={competitionId}
                generationId={article.generation.id}
                active={activeTab === "usage"}
                provisional={false}
              />
            </TabsContent>
          </div>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}

export function Component(): React.JSX.Element {
  const { competitionId, generationId } = useParams();
  const [searchParameters] = useSearchParams();
  const resolvedCompetitionId = competitionId ?? "";
  const resolvedGenerationId = generationId ?? "";
  const validScope =
    resolvedCompetitionId.length > 0 && resolvedGenerationId.length > 0;
  const articleQuery = useSubmittedArticle(
    resolvedCompetitionId,
    resolvedGenerationId,
    validScope,
  );
  const seasonsQuery = useSeasonList(competitionId, seasonListParameters);
  const libraryPage = positiveArticlePage(searchParameters.get("libraryPage"));
  const seasonId = searchParameters.get("season") ?? undefined;
  const kind = articleKind(searchParameters.get("kind"));
  const libraryQuery = useArticleList(competitionId, {
    competitionSeasonId: seasonId,
    kind,
    limit: ARTICLE_PAGE_SIZE,
    offset: (libraryPage - 1) * ARTICLE_PAGE_SIZE,
  });
  const [copyStatus, setCopyStatus] = useState<string>();

  if (articleQuery.isPending) return <ReaderSkeleton />;

  if (articleQuery.isError || !validScope) {
    const missing =
      articleQuery.error instanceof ApiError &&
      articleQuery.error.status === 404;
    return (
      <div className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
        <CircleAlert className="size-8 text-destructive" aria-hidden="true" />
        <h1 className="mt-4 font-editorial text-3xl font-semibold">
          {missing ? "Submitted article not found" : "Article unavailable"}
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          {articleQuery.error instanceof ApiError
            ? articleQuery.error.message
            : "The exact submitted article could not be loaded."}
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          {!missing ? (
            <Button
              variant="outline"
              onClick={() => void articleQuery.refetch()}
            >
              Try again
            </Button>
          ) : null}
          <Link
            className={buttonVariants({ variant: "ghost" })}
            to={
              competitionId
                ? articleLibraryPath(competitionId, searchParameters)
                : "/competitions"
            }
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Back to articles
          </Link>
        </div>
      </div>
    );
  }

  const article = articleQuery.data;
  const split = splitArticle(article.version.content);
  const season = seasonsQuery.data?.page.items.find(
    (item) => item.season.id === article.generation.competition_season_id,
  );
  const libraryItems = libraryQuery.data?.page.items ?? [];
  const currentIndex = libraryItems.findIndex(
    (item) => item.generation_id === resolvedGenerationId,
  );
  const newerArticle =
    currentIndex > 0 ? libraryItems[currentIndex - 1] : undefined;
  const olderArticle =
    currentIndex >= 0 && currentIndex < libraryItems.length - 1
      ? libraryItems[currentIndex + 1]
      : undefined;

  async function copyMarkdown(): Promise<void> {
    try {
      await navigator.clipboard.writeText(article.version.content);
      setCopyStatus("Markdown copied to the clipboard.");
    } catch {
      setCopyStatus(
        "Markdown could not be copied. Select the article text instead.",
      );
    }
  }

  return (
    <div className="mx-auto w-full max-w-5xl px-5 py-8 sm:px-8 sm:py-12">
      <Link
        className={cn(buttonVariants({ variant: "ghost" }), "-ml-3")}
        to={articleLibraryPath(resolvedCompetitionId, searchParameters)}
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Back to articles
      </Link>

      <div className="mx-auto mt-9 max-w-3xl">
        <header className="border-b border-border pb-8 sm:pb-10">
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            <Badge
              variant={
                article.generation.kind === "backtest" ? "secondary" : "outline"
              }
            >
              {article.generation.kind === "backtest"
                ? "Historical backtest"
                : "Live article"}
            </Badge>
            <span>{season?.season.season_year ?? "Season"}</span>
            <span aria-hidden="true">·</span>
            <span>
              {weekLabel(
                article.generation.week_start,
                article.generation.week_end,
              )}
            </span>
          </div>
          <h1 className="mt-5 font-editorial text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">
            {split.title}
          </h1>
          <div className="mt-5 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <p className="text-sm text-muted-foreground">
              Completed{" "}
              <DateTime value={article.generation.completed_at} showExact />
            </p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => void copyMarkdown()}>
                {copyStatus?.startsWith("Markdown copied") ? (
                  <Check className="size-4" aria-hidden="true" />
                ) : (
                  <Copy className="size-4" aria-hidden="true" />
                )}
                Copy Markdown
              </Button>
              <RunDetailsSheet
                article={article}
                competitionId={resolvedCompetitionId}
                seasonYear={season?.season.season_year}
              />
            </div>
          </div>
          {copyStatus ? (
            <p className="mt-3 text-xs text-muted-foreground" role="status">
              {copyStatus}
            </p>
          ) : null}
        </header>

        <section className="py-9 sm:py-12" aria-label="Article content">
          <MarkdownArticle content={split.body} />
        </section>

        <nav
          aria-label="Adjacent articles"
          className="grid gap-3 border-t border-border pt-6 sm:grid-cols-2"
        >
          {newerArticle ? (
            <Link
              className="group rounded-lg border border-border p-4 transition-colors hover:bg-accent"
              to={siblingArticlePath(
                resolvedCompetitionId,
                newerArticle.generation_id,
                searchParameters,
              )}
            >
              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                <ArrowLeft className="size-3" aria-hidden="true" />
                Newer article
              </span>
              <span className="mt-2 block font-editorial text-lg font-semibold leading-snug group-hover:underline">
                {newerArticle.title}
              </span>
            </Link>
          ) : (
            <span />
          )}
          {olderArticle ? (
            <Link
              className="group rounded-lg border border-border p-4 text-right transition-colors hover:bg-accent"
              to={siblingArticlePath(
                resolvedCompetitionId,
                olderArticle.generation_id,
                searchParameters,
              )}
            >
              <span className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
                Older article
                <ArrowRight className="size-3" aria-hidden="true" />
              </span>
              <span className="mt-2 block font-editorial text-lg font-semibold leading-snug group-hover:underline">
                {olderArticle.title}
              </span>
            </Link>
          ) : null}
        </nav>

        <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-6">
          <Link
            className={buttonVariants({ variant: "ghost" })}
            to={articleLibraryPath(resolvedCompetitionId, searchParameters)}
          >
            View all articles
          </Link>
          <Link
            className={buttonVariants({ variant: "default" })}
            to={`/competitions/${resolvedCompetitionId}/generate?season=${article.generation.competition_season_id}`}
          >
            Generate another article
          </Link>
        </footer>
      </div>
    </div>
  );
}
