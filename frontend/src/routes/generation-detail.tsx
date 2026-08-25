import {
  ArrowLeft,
  CircleAlert,
  CircleCheck,
  CircleX,
  Clock3,
  FileText,
  LoaderCircle,
  Pencil,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import { ApiError } from "@/api/errors";
import { DateTime } from "@/components/shared/date-time";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SubmittedArticlePanel } from "@/features/articles/submitted-article-panel";
import { ArtifactBrowser } from "@/features/artifacts/artifact-browser";
import {
  createGenerationFormValuesFromDetail,
  saveGenerationDraft,
} from "@/features/generations/draft";
import {
  useGenerationDetail,
  useRerunGeneration,
} from "@/features/generations/queries";
import { useSeasonList } from "@/features/seasons/queries";
import { cn } from "@/lib/utils";

const seasonListParameters = { limit: 200, offset: 0 } as const;
const detailTabs = ["article", "artifacts", "execution", "usage"] as const;
type DetailTab = (typeof detailTabs)[number];

function detailTab(value: string | null, submitted: boolean): DetailTab {
  if (detailTabs.some((candidate) => candidate === value)) {
    if (value === "article" && !submitted) return "execution";
    return value as DetailTab;
  }
  return submitted ? "article" : "execution";
}

function titleCase(value: string): string {
  return value
    .split(/[_\-.\s]+/u)
    .filter(Boolean)
    .map((part) => `${part[0]?.toUpperCase() ?? ""}${part.slice(1)}`)
    .join(" ");
}

function elapsedLabel(start: string, end?: string | null): string {
  const elapsedSeconds = Math.max(
    0,
    Math.floor(
      (new Date(end ?? Date.now()).getTime() - new Date(start).getTime()) /
        1_000,
    ),
  );
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  if (minutes < 1) return `${String(seconds)}s`;
  const hours = Math.floor(minutes / 60);
  if (hours < 1) return `${String(minutes)}m ${String(seconds)}s`;
  return `${String(hours)}h ${String(minutes % 60)}m`;
}

function statusVariant(
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled",
): "default" | "outline" | "destructive" {
  if (status === "failed") return "destructive";
  if (status === "succeeded") return "default";
  return "outline";
}

function DetailSkeleton(): React.JSX.Element {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-5 py-10 sm:px-8 sm:py-14">
      <Skeleton className="h-10 w-72" />
      <Skeleton className="h-44 w-full" />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Skeleton className="h-72 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    </div>
  );
}

export function Component(): React.JSX.Element {
  const { competitionId, generationId } = useParams();
  const navigate = useNavigate();
  const [searchParameters, setSearchParameters] = useSearchParams();
  const resolvedCompetitionId = competitionId ?? "";
  const resolvedGenerationId = generationId ?? "";
  const detailQuery = useGenerationDetail(resolvedCompetitionId, generationId);
  const seasonsQuery = useSeasonList(competitionId, seasonListParameters);
  const rerun = useRerunGeneration(resolvedCompetitionId, resolvedGenerationId);

  if (detailQuery.isPending) return <DetailSkeleton />;

  if (detailQuery.isError || !competitionId || !generationId) {
    const missing =
      detailQuery.error instanceof ApiError && detailQuery.error.status === 404;
    return (
      <div className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
        <CircleAlert className="size-8 text-destructive" aria-hidden="true" />
        <h1 className="mt-4 font-editorial text-3xl font-semibold">
          {missing ? "Run not found" : "Run detail unavailable"}
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          {detailQuery.error instanceof ApiError
            ? detailQuery.error.message
            : "The durable generation record could not be loaded."}
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          {!missing ? (
            <Button
              variant="outline"
              onClick={() => void detailQuery.refetch()}
            >
              Try again
            </Button>
          ) : null}
          <Link
            className={buttonVariants({ variant: "ghost" })}
            to={
              competitionId
                ? `/competitions/${competitionId}/generate`
                : "/competitions"
            }
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Back to Generate
          </Link>
        </div>
      </div>
    );
  }

  const generation = detailQuery.data.generation;
  const terminal = ["succeeded", "failed", "cancelled"].includes(
    generation.status,
  );
  const active =
    generation.status === "pending" || generation.status === "running";
  const editableValues = createGenerationFormValuesFromDetail(generation);
  const season = seasonsQuery.data?.page.items.find(
    (item) => item.season.id === generation.competition_season_id,
  );
  const fallbackModels = editableValues?.model.fallbackModels ?? [];
  const progressStart = generation.started_at ?? generation.created_at;
  const submitted = generation.submitted_artifact_version_id !== null;
  const activeTab = detailTab(searchParameters.get("tab"), submitted);

  function selectTab(nextTab: string): void {
    const next = new URLSearchParams(searchParameters);
    next.set("tab", nextTab);
    next.delete("artifact");
    next.delete("version");
    next.delete("artifactPage");
    next.delete("versionPage");
    next.delete("page");
    setSearchParameters(next, { replace: true });
  }

  async function rerunGeneration(): Promise<void> {
    try {
      const response = await rerun.mutateAsync();
      toast.success("Rerun queued");
      await navigate(
        `/competitions/${resolvedCompetitionId}/generations/${response.generation.id}`,
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
    saveGenerationDraft(resolvedCompetitionId, editableValues);
    void navigate(
      `/competitions/${resolvedCompetitionId}/generate?season=${generation.competition_season_id}`,
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <header className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              Generation record
            </p>
            <Badge variant={statusVariant(generation.status)}>
              {titleCase(generation.status)}
            </Badge>
          </div>
          <h1 className="mt-3 font-editorial text-4xl font-semibold tracking-tight sm:text-5xl">
            {generation.status === "succeeded"
              ? "Article ready"
              : generation.status === "failed"
                ? "Generation failed"
                : generation.status === "cancelled"
                  ? "Generation cancelled"
                  : "Generating article"}
          </h1>
          <p className="mt-3 max-w-2xl break-words text-sm leading-6 text-muted-foreground">
            {generation.request_text}
          </p>
        </div>
        {terminal ? (
          <div className="flex flex-wrap gap-2">
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
          </div>
        ) : null}
      </header>

      {active ? (
        <section
          className="mt-9 overflow-hidden rounded-lg border border-primary/25 bg-card"
          aria-live="polite"
          aria-atomic="true"
        >
          <div className="flex items-start gap-4 p-5 sm:p-6">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
              {generation.status === "running" ? (
                <RefreshCw className="size-5 animate-spin" aria-hidden="true" />
              ) : (
                <Clock3 className="size-5" aria-hidden="true" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                {generation.status === "pending"
                  ? "Waiting for worker"
                  : "Reporter running"}
              </p>
              <h2 className="mt-2 font-editorial text-2xl font-semibold">
                {generation.current_stage
                  ? titleCase(generation.current_stage)
                  : "Preparing durable inputs"}
              </h2>
              <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted-foreground">
                <span>Turn {generation.current_turn}</span>
                <span>Elapsed {elapsedLabel(progressStart)}</span>
                {generation.progress_updated_at ? (
                  <span>
                    Updated <DateTime value={generation.progress_updated_at} />
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          <div className="h-1 overflow-hidden bg-muted">
            <div className="h-full w-1/3 animate-pulse bg-primary" />
          </div>
        </section>
      ) : null}

      {generation.status === "succeeded" ? (
        <section className="mt-9 rounded-lg border border-primary/25 bg-primary/5 p-5 sm:p-6">
          <div className="flex gap-4">
            <CircleCheck
              className="mt-0.5 size-6 shrink-0 text-primary"
              aria-hidden="true"
            />
            <div>
              <h2 className="font-editorial text-2xl font-semibold">
                Submitted article recorded
              </h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                The exact submitted artifact version is attached to this durable
                run and available in the Article tab below.
              </p>
            </div>
          </div>
        </section>
      ) : null}

      {generation.status === "failed" || generation.status === "cancelled" ? (
        <section className="mt-9 rounded-lg border border-destructive/30 bg-destructive/5 p-5 sm:p-6">
          <div className="flex gap-4">
            <CircleX
              className="mt-0.5 size-6 shrink-0 text-destructive"
              aria-hidden="true"
            />
            <div>
              <h2 className="font-editorial text-2xl font-semibold">
                {generation.status === "failed"
                  ? "Run did not complete"
                  : "Run was cancelled"}
              </h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {generation.failure_summary ??
                  "No additional failure detail was recorded for this run."}
              </p>
              {generation.failure_category ? (
                <p className="mt-3 font-mono text-xs text-muted-foreground">
                  {generation.failure_category}
                </p>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section className="rounded-lg border border-border bg-card p-5 sm:p-6">
          <div className="flex items-center gap-2">
            <FileText
              className="size-4 text-muted-foreground"
              aria-hidden="true"
            />
            <h2 className="font-editorial text-2xl font-semibold">
              Assignment
            </h2>
          </div>
          <p className="mt-5 whitespace-pre-wrap text-sm leading-7">
            {generation.request_text}
          </p>
          <dl className="mt-6 grid gap-5 border-t border-border pt-5 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-muted-foreground">Primary model</dt>
              <dd className="mt-1 break-all font-medium">
                {generation.requested_primary_model}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Fallback chain</dt>
              <dd className="mt-1 font-medium">
                {editableValues
                  ? fallbackModels.length > 0
                    ? fallbackModels.join(" → ")
                    : "None"
                  : "Saved settings schema unsupported"}
              </dd>
            </div>
          </dl>
          {!editableValues ? (
            <p className="mt-5 rounded-md border border-border bg-muted/60 p-4 text-xs leading-5 text-muted-foreground">
              These saved settings cannot be safely decoded by this frontend, so
              Edit settings is disabled. Exact rerun remains available for
              terminal runs because the backend owns that copy operation.
            </p>
          ) : null}
        </section>

        <aside className="rounded-lg border border-border bg-card p-5">
          <h2 className="font-semibold">Run metadata</h2>
          <dl className="mt-5 space-y-4 text-sm">
            <div className="flex items-start justify-between gap-4">
              <dt className="text-muted-foreground">Season</dt>
              <dd className="text-right font-medium">
                {season?.season.season_year ?? generation.competition_season_id}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
              <dt className="text-muted-foreground">Weeks</dt>
              <dd className="text-right font-medium">
                {generation.week_start === generation.week_end
                  ? `Week ${String(generation.week_start ?? "—")}`
                  : `${String(generation.week_start ?? "—")}–${String(generation.week_end ?? "—")}`}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
              <dt className="text-muted-foreground">Mode</dt>
              <dd className="text-right font-medium">
                {titleCase(generation.kind)}
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
              <dt className="text-muted-foreground">Created</dt>
              <dd className="text-right">
                <DateTime value={generation.created_at} showExact />
              </dd>
            </div>
            <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
              <dt className="text-muted-foreground">Elapsed</dt>
              <dd className="text-right font-medium">
                {elapsedLabel(progressStart, generation.completed_at)}
              </dd>
            </div>
            {generation.rerun_of_generation_id ? (
              <div className="border-t border-border pt-4">
                <dt className="text-muted-foreground">Rerun of</dt>
                <dd className="mt-1 break-all">
                  <Link
                    className="text-primary underline-offset-4 hover:underline"
                    to={`/competitions/${resolvedCompetitionId}/generations/${generation.rerun_of_generation_id}`}
                  >
                    {generation.rerun_of_generation_id}
                  </Link>
                </dd>
              </div>
            ) : null}
          </dl>
        </aside>
      </div>

      <section className="mt-10" aria-labelledby="generation-work-heading">
        <div className="mb-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Durable work record
          </p>
          <h2
            id="generation-work-heading"
            className="mt-2 font-editorial text-3xl font-semibold"
          >
            Article and audit
          </h2>
        </div>
        <Tabs value={activeTab} onValueChange={selectTab}>
          <div className="overflow-x-auto pb-1">
            <TabsList className="min-w-max">
              <TabsTrigger value="article" disabled={!submitted}>
                Article
              </TabsTrigger>
              <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
              <TabsTrigger value="execution">Execution</TabsTrigger>
              <TabsTrigger value="usage">Usage</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="article" className="min-w-0">
            <SubmittedArticlePanel
              key={resolvedGenerationId}
              competitionId={resolvedCompetitionId}
              generationId={resolvedGenerationId}
              seasonYear={season?.season.season_year}
              submitted={submitted}
              active={activeTab === "article"}
            />
          </TabsContent>
          <TabsContent value="artifacts">
            <ArtifactBrowser
              key={resolvedGenerationId}
              competitionId={resolvedCompetitionId}
              generationId={resolvedGenerationId}
              submittedVersionId={generation.submitted_artifact_version_id}
              active={activeTab === "artifacts"}
            />
          </TabsContent>
          <TabsContent value="execution">
            <DeferredAuditPanel
              title="Execution timeline"
              description="The durable run status remains above. Turn, AI-call, and nested tool-call inspection lands in the execution audit slice."
            />
          </TabsContent>
          <TabsContent value="usage">
            <DeferredAuditPanel
              title="Usage and estimated cost"
              description="Backend-owned token and cost estimates land with the execution audit slice."
            />
          </TabsContent>
        </Tabs>
      </section>

      <div className="mt-8">
        <Link
          className={cn(buttonVariants({ variant: "ghost" }), "px-0")}
          to={`/competitions/${resolvedCompetitionId}/generate?season=${generation.competition_season_id}`}
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Back to Generate
        </Link>
      </div>
    </div>
  );
}

function DeferredAuditPanel({
  title,
  description,
}: {
  title: string;
  description: string;
}): React.JSX.Element {
  return (
    <div className="rounded-lg border border-dashed border-border bg-card/60 p-7 sm:p-9">
      <h3 className="font-editorial text-2xl font-semibold">{title}</h3>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
        {description}
      </p>
    </div>
  );
}
