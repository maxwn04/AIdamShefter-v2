import { Check, CircleAlert, Copy, FileText } from "lucide-react";
import { useState } from "react";

import { ApiError } from "@/api/errors";
import { MarkdownArticle } from "@/components/shared/markdown-article";
import { DateTime } from "@/components/shared/date-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSubmittedArticle } from "@/features/articles/queries";
import { createGenerationFormValuesFromDetail } from "@/features/generations/draft";

interface SubmittedArticlePanelProps {
  competitionId: string;
  generationId: string;
  seasonYear?: number;
  submitted: boolean;
  active: boolean;
}

function titleCase(value: string): string {
  return value
    .split(/[_\-.\s]+/u)
    .filter(Boolean)
    .map((part) => `${part[0]?.toUpperCase() ?? ""}${part.slice(1)}`)
    .join(" ");
}

function weekLabel(start: number | null, end: number | null): string {
  if (start === null || end === null) return "Not recorded";
  return start === end
    ? `Week ${String(start)}`
    : `Weeks ${String(start)}–${String(end)}`;
}

function ArticleSkeleton(): React.JSX.Element {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <div className="space-y-4 rounded-lg border border-border bg-card p-6 sm:p-8">
        <Skeleton className="h-10 w-4/5" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-11/12" />
        <Skeleton className="h-40 w-full" />
      </div>
      <Skeleton className="h-96 w-full rounded-lg" />
    </div>
  );
}

export function SubmittedArticlePanel({
  competitionId,
  generationId,
  seasonYear,
  submitted,
  active,
}: SubmittedArticlePanelProps): React.JSX.Element {
  const articleQuery = useSubmittedArticle(
    competitionId,
    generationId,
    active && submitted,
  );
  const [copyStatus, setCopyStatus] = useState<string>();

  if (!submitted) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-card/60 p-8 text-center sm:p-12">
        <FileText
          className="mx-auto size-7 text-muted-foreground"
          aria-hidden="true"
        />
        <h2 className="mt-4 font-editorial text-2xl font-semibold">
          No submitted article
        </h2>
        <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
          This run has not recorded an exact submitted artifact version. Its
          status and audit data remain available on this generation record.
        </p>
      </div>
    );
  }

  if (articleQuery.isPending) return <ArticleSkeleton />;

  if (articleQuery.isError) {
    const missing =
      articleQuery.error instanceof ApiError &&
      articleQuery.error.status === 404;
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
        <CircleAlert className="size-6 text-destructive" aria-hidden="true" />
        <h2 className="mt-3 font-editorial text-2xl font-semibold">
          {missing ? "Submitted article not found" : "Article unavailable"}
        </h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {articleQuery.error instanceof ApiError
            ? articleQuery.error.message
            : "The exact submitted article could not be loaded."}
        </p>
        {!missing ? (
          <Button
            className="mt-5"
            variant="outline"
            onClick={() => void articleQuery.refetch()}
          >
            Try again
          </Button>
        ) : null}
      </div>
    );
  }

  const { generation, artifact, version } = articleQuery.data;
  const decodedSettings = createGenerationFormValuesFromDetail(generation);
  const fallbackModels = decodedSettings?.model.fallbackModels ?? [];

  async function copyMarkdown(): Promise<void> {
    try {
      await navigator.clipboard.writeText(version.content);
      setCopyStatus("Markdown copied to the clipboard.");
    } catch {
      setCopyStatus(
        "Markdown could not be copied. Select the article text instead.",
      );
    }
  }

  return (
    <div className="grid min-w-0 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
      <section className="min-w-0 overflow-hidden rounded-lg border border-border bg-card">
        <div className="flex flex-col gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              Exact submitted version
            </p>
            <p className="mt-1 break-all text-xs text-muted-foreground">
              Revision {version.revision_number} · {artifact.path}
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void copyMarkdown()}
          >
            {copyStatus?.startsWith("Markdown copied") ? (
              <Check className="size-4" aria-hidden="true" />
            ) : (
              <Copy className="size-4" aria-hidden="true" />
            )}
            Copy Markdown
          </Button>
        </div>
        <div className="px-5 py-7 sm:px-8 sm:py-10">
          <MarkdownArticle content={version.content} />
        </div>
        {copyStatus ? (
          <p
            className="border-t border-border px-5 py-3 text-xs text-muted-foreground sm:px-8"
            role="status"
          >
            {copyStatus}
          </p>
        ) : null}
      </section>

      <aside className="min-w-0 rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Article metadata</h2>
          <Badge variant="outline">{titleCase(generation.kind)}</Badge>
        </div>
        <dl className="mt-5 space-y-4 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">Assignment</dt>
            <dd className="mt-1 whitespace-pre-wrap break-words leading-6">
              {generation.request_text}
            </dd>
          </div>
          <div className="grid grid-cols-2 gap-4 border-t border-border pt-4">
            <div>
              <dt className="text-xs text-muted-foreground">Season</dt>
              <dd className="mt-1 font-medium">
                {seasonYear ?? generation.competition_season_id}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Scope</dt>
              <dd className="mt-1 font-medium">
                {weekLabel(generation.week_start, generation.week_end)}
              </dd>
            </div>
          </div>
          <div className="border-t border-border pt-4">
            <dt className="text-xs text-muted-foreground">Completed</dt>
            <dd className="mt-1">
              <DateTime value={generation.completed_at} showExact />
            </dd>
          </div>
          <div className="border-t border-border pt-4">
            <dt className="text-xs text-muted-foreground">Model chain</dt>
            <dd className="mt-1 break-all font-medium">
              {generation.requested_primary_model}
              {fallbackModels.length > 0
                ? ` → ${fallbackModels.join(" → ")}`
                : ""}
            </dd>
          </div>
          <div className="border-t border-border pt-4">
            <dt className="text-xs text-muted-foreground">Snapshot</dt>
            <dd className="mt-1 break-all font-mono text-xs">
              {generation.data_snapshot_id ?? "Not recorded"}
            </dd>
          </div>
          <div className="border-t border-border pt-4">
            <dt className="text-xs text-muted-foreground">Memory input</dt>
            <dd className="mt-1 break-all font-mono text-xs">
              {generation.input_memory_revision_id ??
                generation.input_memory_artifact_version_id ??
                "No persisted memory input"}
            </dd>
          </div>
          {generation.manifest_hash ? (
            <div className="border-t border-border pt-4">
              <dt className="text-xs text-muted-foreground">Manifest hash</dt>
              <dd className="mt-1 break-all font-mono text-xs">
                {generation.manifest_hash}
              </dd>
            </div>
          ) : null}
          <div className="border-t border-border pt-4">
            <dt className="text-xs text-muted-foreground">Content hash</dt>
            <dd className="mt-1 break-all font-mono text-xs">
              {version.content_hash}
            </dd>
          </div>
        </dl>
      </aside>
    </div>
  );
}
