import {
  ArrowLeft,
  ArrowRight,
  CircleAlert,
  FileArchive,
  FileText,
} from "lucide-react";
import { useEffect } from "react";
import { useSearchParams } from "react-router";

import { ApiError } from "@/api/errors";
import { ArtifactContentViewer } from "@/components/shared/artifact-content-viewer";
import { DateTime } from "@/components/shared/date-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSubmittedArticle } from "@/features/articles/queries";
import type {
  Artifact,
  ArtifactSummary,
  ArtifactVersionSummary,
} from "@/features/artifacts/api";
import {
  useArtifactList,
  useArtifactVersion,
  useArtifactVersionList,
} from "@/features/artifacts/queries";
import { cn } from "@/lib/utils";

const ARTIFACT_PAGE_SIZE = 25;
const VERSION_PAGE_SIZE = 25;

interface ArtifactBrowserProps {
  competitionId: string;
  generationId: string;
  submittedVersionId: string | null;
  active: boolean;
}

function positivePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

function artifactIsSummary(
  artifact: Artifact | ArtifactSummary,
): artifact is ArtifactSummary {
  return "revision_count" in artifact;
}

function artifactRevisionCount(
  artifact: Artifact | ArtifactSummary,
  versionTotal: number | undefined,
): string {
  const count = artifactIsSummary(artifact)
    ? artifact.revision_count
    : versionTotal;
  if (count === undefined) return "Revisions unavailable";
  return `${String(count)} revision${count === 1 ? "" : "s"}`;
}

function BrowserSkeleton(): React.JSX.Element {
  return (
    <div className="grid gap-6 lg:grid-cols-[19rem_minmax(0,1fr)]">
      <div className="space-y-3">
        {[0, 1, 2].map((item) => (
          <Skeleton key={item} className="h-28 w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-[32rem] w-full rounded-lg" />
    </div>
  );
}

function InlineError({
  title,
  error,
  onRetry,
}: {
  title: string;
  error: unknown;
  onRetry: () => void;
}): React.JSX.Element {
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-6">
      <CircleAlert className="size-6 text-destructive" aria-hidden="true" />
      <h3 className="mt-3 font-semibold">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">
        {error instanceof ApiError
          ? error.message
          : "This durable artifact resource could not be loaded."}
      </p>
      <Button className="mt-4" variant="outline" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

function Pager({
  label,
  page,
  totalPages,
  total,
  onPageChange,
}: {
  label: string;
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
}): React.JSX.Element | null {
  if (totalPages <= 1) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 text-xs">
      <span className="text-muted-foreground">
        {label} page {page} of {totalPages} · {total} total
      </span>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1}
          aria-label={`Previous ${label.toLowerCase()} page`}
          onClick={() => {
            onPageChange(page - 1);
          }}
        >
          <ArrowLeft className="size-4" aria-hidden="true" />
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={page >= totalPages}
          aria-label={`Next ${label.toLowerCase()} page`}
          onClick={() => {
            onPageChange(page + 1);
          }}
        >
          Next
          <ArrowRight className="size-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

function ArtifactChoice({
  artifact,
  selected,
  submitted,
  onSelect,
}: {
  artifact: ArtifactSummary;
  selected: boolean;
  submitted: boolean;
  onSelect: () => void;
}): React.JSX.Element {
  return (
    <button
      type="button"
      className={cn(
        "w-full rounded-lg border border-border bg-card p-4 text-left outline-none transition-colors hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring",
        selected && "border-primary/50 bg-accent/55",
      )}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="flex flex-wrap items-center gap-2">
        {submitted ? <Badge>Submitted</Badge> : null}
        {artifact.finalized_version_id ? (
          <Badge variant="outline">Finalized</Badge>
        ) : (
          <Badge variant="secondary">Draft</Badge>
        )}
      </span>
      <span className="mt-3 block break-all font-mono text-sm font-medium">
        {artifact.path}
      </span>
      <span className="mt-2 block text-xs text-muted-foreground">
        {artifact.media_type} · {artifactRevisionCount(artifact, undefined)}
      </span>
      <span className="mt-1 block text-xs text-muted-foreground">
        Updated <DateTime value={artifact.latest_version_at} />
      </span>
    </button>
  );
}

function VersionChoice({
  version,
  selected,
  submitted,
  finalized,
  onSelect,
}: {
  version: ArtifactVersionSummary;
  selected: boolean;
  submitted: boolean;
  finalized: boolean;
  onSelect: () => void;
}): React.JSX.Element {
  return (
    <button
      type="button"
      className={cn(
        "w-full rounded-md border border-border bg-background p-3 text-left outline-none transition-colors hover:bg-muted/55 focus-visible:ring-2 focus-visible:ring-ring",
        selected && "border-primary/50 bg-accent/55",
      )}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="flex flex-wrap items-center gap-2">
        <span className="font-medium">Revision {version.revision_number}</span>
        {submitted ? <Badge>Submitted</Badge> : null}
        {finalized ? <Badge variant="outline">Finalized</Badge> : null}
      </span>
      <span className="mt-2 block text-xs text-muted-foreground">
        <DateTime value={version.created_at} showExact />
      </span>
      {version.source_ai_call_id || version.source_tool_call_id ? (
        <span className="mt-2 block text-xs text-muted-foreground">
          Source: {version.source_tool_call_id ? "tool call" : "AI call"}
        </span>
      ) : null}
    </button>
  );
}

export function ArtifactBrowser({
  competitionId,
  generationId,
  submittedVersionId,
  active,
}: ArtifactBrowserProps): React.JSX.Element {
  const [searchParameters, setSearchParameters] = useSearchParams();
  const artifactPage = positivePage(searchParameters.get("artifactPage"));
  const requestedArtifactId = searchParameters.get("artifact") ?? undefined;
  const requestedVersionId = searchParameters.get("version") ?? undefined;
  const submittedArticleQuery = useSubmittedArticle(
    competitionId,
    generationId,
    active && submittedVersionId !== null,
  );
  const artifactsQuery = useArtifactList(
    competitionId,
    generationId,
    {
      limit: ARTIFACT_PAGE_SIZE,
      offset: (artifactPage - 1) * ARTIFACT_PAGE_SIZE,
    },
    active,
  );
  const artifacts = artifactsQuery.data?.page.items ?? [];
  const submittedArtifact = submittedArticleQuery.data?.artifact;
  const submittedArtifactId = submittedArtifact?.id;
  const selectionReady =
    submittedVersionId === null || !submittedArticleQuery.isPending;
  const requestedArtifact = artifacts.find(
    (artifact) => artifact.id === requestedArtifactId,
  );
  const selectedArtifactId = selectionReady
    ? (requestedArtifact?.id ??
      (requestedArtifactId === submittedArtifactId
        ? submittedArtifactId
        : undefined) ??
      submittedArtifactId ??
      artifacts[0]?.id)
    : undefined;
  const selectedArtifact =
    artifacts.find((artifact) => artifact.id === selectedArtifactId) ??
    (submittedArtifact?.id === selectedArtifactId
      ? submittedArtifact
      : undefined);
  const submittedRevision = submittedArticleQuery.data?.version;
  const implicitSubmittedVersionPage =
    submittedRevision && selectedArtifactId === submittedArtifactId
      ? Math.max(
          1,
          Math.ceil(submittedRevision.revision_number / VERSION_PAGE_SIZE),
        )
      : 1;
  const versionPageParameter = searchParameters.get("versionPage");
  const versionPage = versionPageParameter
    ? positivePage(versionPageParameter)
    : implicitSubmittedVersionPage;
  const versionsQuery = useArtifactVersionList(
    competitionId,
    generationId,
    selectedArtifactId,
    {
      limit: VERSION_PAGE_SIZE,
      offset: (versionPage - 1) * VERSION_PAGE_SIZE,
    },
    active && selectedArtifactId !== undefined,
  );
  const versions = versionsQuery.data?.page.items ?? [];
  const requestedVersion = versions.find(
    (version) => version.id === requestedVersionId,
  );
  const requestedSubmittedVersion =
    requestedVersionId === submittedVersionId &&
    selectedArtifactId === submittedArtifactId
      ? submittedRevision
      : undefined;
  const selectedVersionId =
    requestedVersion?.id ??
    requestedSubmittedVersion?.id ??
    (selectedArtifactId === submittedArtifactId
      ? (submittedVersionId ?? undefined)
      : (selectedArtifact?.finalized_version_id ?? versions.at(-1)?.id));
  const selectedSubmittedVersion =
    selectedVersionId === submittedVersionId &&
    selectedArtifactId === submittedArtifactId
      ? submittedRevision
      : undefined;
  const selectedVersionQuery = useArtifactVersion(
    competitionId,
    generationId,
    selectedArtifactId,
    selectedVersionId,
    active && selectedSubmittedVersion === undefined,
  );
  const selectedVersion =
    selectedSubmittedVersion ?? selectedVersionQuery.data?.version;
  const artifactTotalPages = pageCount(
    artifactsQuery.data?.page.total ?? 0,
    ARTIFACT_PAGE_SIZE,
  );
  const versionTotalPages = pageCount(
    versionsQuery.data?.page.total ?? 0,
    VERSION_PAGE_SIZE,
  );

  useEffect(() => {
    if (!active || !artifactsQuery.data || artifactPage <= artifactTotalPages)
      return;
    const next = new URLSearchParams(searchParameters);
    if (artifactTotalPages === 1) next.delete("artifactPage");
    else next.set("artifactPage", String(artifactTotalPages));
    next.delete("artifact");
    next.delete("version");
    next.delete("versionPage");
    setSearchParameters(next, { replace: true });
  }, [
    active,
    artifactPage,
    artifactTotalPages,
    artifactsQuery.data,
    searchParameters,
    setSearchParameters,
  ]);

  useEffect(() => {
    if (!active || !selectedArtifactId) return;
    const next = new URLSearchParams(searchParameters);
    let changed = false;
    if (next.get("artifact") !== selectedArtifactId) {
      next.set("artifact", selectedArtifactId);
      changed = true;
    }
    if (!versionPageParameter && implicitSubmittedVersionPage > 1) {
      next.set("versionPage", String(implicitSubmittedVersionPage));
      changed = true;
    }
    if (selectedVersionId && next.get("version") !== selectedVersionId) {
      next.set("version", selectedVersionId);
      changed = true;
    }
    if (changed) setSearchParameters(next, { replace: true });
  }, [
    active,
    implicitSubmittedVersionPage,
    searchParameters,
    selectedArtifactId,
    selectedVersionId,
    setSearchParameters,
    versionPageParameter,
  ]);

  useEffect(() => {
    if (!active || !versionsQuery.data || versionPage <= versionTotalPages)
      return;
    const next = new URLSearchParams(searchParameters);
    if (versionTotalPages === 1) next.delete("versionPage");
    else next.set("versionPage", String(versionTotalPages));
    next.delete("version");
    setSearchParameters(next, { replace: true });
  }, [
    active,
    searchParameters,
    setSearchParameters,
    versionPage,
    versionTotalPages,
    versionsQuery.data,
  ]);

  function selectArtifact(artifactId: string): void {
    const next = new URLSearchParams(searchParameters);
    next.set("artifact", artifactId);
    next.delete("version");
    next.delete("versionPage");
    setSearchParameters(next);
  }

  function selectVersion(versionId: string): void {
    const next = new URLSearchParams(searchParameters);
    next.set("version", versionId);
    setSearchParameters(next);
  }

  function setArtifactPage(nextPage: number): void {
    const next = new URLSearchParams(searchParameters);
    if (nextPage === 1) next.delete("artifactPage");
    else next.set("artifactPage", String(nextPage));
    next.delete("artifact");
    next.delete("version");
    next.delete("versionPage");
    setSearchParameters(next);
  }

  function setVersionPage(nextPage: number): void {
    const next = new URLSearchParams(searchParameters);
    if (nextPage === 1) next.delete("versionPage");
    else next.set("versionPage", String(nextPage));
    setSearchParameters(next);
  }

  if (artifactsQuery.isPending || !selectionReady) return <BrowserSkeleton />;

  if (artifactsQuery.isError) {
    return (
      <InlineError
        title="Artifact history unavailable"
        error={artifactsQuery.error}
        onRetry={() => void artifactsQuery.refetch()}
      />
    );
  }

  if (artifacts.length === 0 && artifactPage === 1) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-card/60 p-8 text-center sm:p-12">
        <FileArchive
          className="mx-auto size-8 text-muted-foreground"
          aria-hidden="true"
        />
        <h3 className="mt-5 font-editorial text-2xl font-semibold">
          No artifacts recorded
        </h3>
        <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
          This generation has no durable work products to inspect.
        </p>
      </div>
    );
  }

  return (
    <div className="grid min-w-0 items-start gap-6 lg:grid-cols-[19rem_minmax(0,1fr)]">
      <section aria-labelledby="artifact-list-heading" className="min-w-0">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 id="artifact-list-heading" className="font-semibold">
            Artifacts
          </h3>
          <span className="text-xs text-muted-foreground">
            {artifactsQuery.data.page.total} total
          </span>
        </div>
        <div className="space-y-3">
          {artifacts.map((artifact) => (
            <ArtifactChoice
              key={artifact.id}
              artifact={artifact}
              selected={artifact.id === selectedArtifactId}
              submitted={artifact.id === submittedArtifactId}
              onSelect={() => {
                selectArtifact(artifact.id);
              }}
            />
          ))}
        </div>
        <div className="mt-4">
          <Pager
            label="Artifacts"
            page={artifactPage}
            totalPages={artifactTotalPages}
            total={artifactsQuery.data.page.total}
            onPageChange={setArtifactPage}
          />
        </div>
      </section>

      <section className="min-w-0 overflow-hidden rounded-lg border border-border bg-card">
        {selectedArtifact ? (
          <>
            <header className="border-b border-border px-5 py-5 sm:px-6">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                    Selected artifact
                  </p>
                  <h3 className="mt-2 break-all font-mono text-base font-semibold">
                    {selectedArtifact.path}
                  </h3>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {selectedArtifact.media_type} ·{" "}
                    {artifactRevisionCount(
                      selectedArtifact,
                      versionsQuery.data?.page.total,
                    )}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {selectedArtifact.id === submittedArtifactId ? (
                    <Badge>Submitted artifact</Badge>
                  ) : null}
                  {selectedArtifact.finalized_version_id ? (
                    <Badge variant="outline">Finalized</Badge>
                  ) : (
                    <Badge variant="secondary">Draft</Badge>
                  )}
                </div>
              </div>
            </header>

            <div className="grid min-w-0 gap-6 p-5 sm:p-6 xl:grid-cols-[15rem_minmax(0,1fr)]">
              <div className="min-w-0">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h4 className="font-semibold">Versions</h4>
                  {versionsQuery.isFetching && !versionsQuery.isPending ? (
                    <span
                      className="text-xs text-muted-foreground"
                      role="status"
                    >
                      Updating…
                    </span>
                  ) : null}
                </div>
                {versionsQuery.isPending ? (
                  <div className="space-y-2">
                    <Skeleton className="h-20 w-full" />
                    <Skeleton className="h-20 w-full" />
                  </div>
                ) : versionsQuery.isError ? (
                  <InlineError
                    title="Version history unavailable"
                    error={versionsQuery.error}
                    onRetry={() => void versionsQuery.refetch()}
                  />
                ) : versions.length === 0 ? (
                  <p className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
                    This artifact has no recorded versions.
                  </p>
                ) : (
                  <>
                    <div className="space-y-2">
                      {versions.map((version) => (
                        <VersionChoice
                          key={version.id}
                          version={version}
                          selected={version.id === selectedVersionId}
                          submitted={version.id === submittedVersionId}
                          finalized={
                            version.id === selectedArtifact.finalized_version_id
                          }
                          onSelect={() => {
                            selectVersion(version.id);
                          }}
                        />
                      ))}
                    </div>
                    <div className="mt-4">
                      <Pager
                        label="Versions"
                        page={versionPage}
                        totalPages={versionTotalPages}
                        total={versionsQuery.data.page.total}
                        onPageChange={setVersionPage}
                      />
                    </div>
                  </>
                )}
              </div>

              <div className="min-w-0">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <h4 className="font-semibold">
                    {selectedVersion
                      ? `Revision ${String(selectedVersion.revision_number)}`
                      : "Version content"}
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {selectedVersion?.id === submittedVersionId ? (
                      <Badge>Submitted</Badge>
                    ) : null}
                    {selectedVersion?.id ===
                    selectedArtifact.finalized_version_id ? (
                      <Badge variant="outline">Finalized</Badge>
                    ) : null}
                  </div>
                </div>
                {selectedVersionId !== undefined &&
                selectedVersionQuery.isPending &&
                !selectedSubmittedVersion ? (
                  <Skeleton className="h-80 w-full rounded-lg" />
                ) : selectedVersionQuery.isError ? (
                  <InlineError
                    title="Version content unavailable"
                    error={selectedVersionQuery.error}
                    onRetry={() => void selectedVersionQuery.refetch()}
                  />
                ) : selectedVersion ? (
                  <>
                    <div className="mb-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">
                      <span>
                        Created <DateTime value={selectedVersion.created_at} />
                      </span>
                      <span className="break-all font-mono">
                        SHA-256 {selectedVersion.content_hash}
                      </span>
                    </div>
                    <ArtifactContentViewer
                      key={selectedVersion.id}
                      content={selectedVersion.content}
                      mediaType={selectedArtifact.media_type}
                    />
                  </>
                ) : (
                  <div className="rounded-lg border border-dashed border-border p-8 text-center">
                    <FileText
                      className="mx-auto size-6 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <p className="mt-3 text-sm text-muted-foreground">
                      Select a version to inspect its exact stored content.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="p-8 text-center text-sm text-muted-foreground">
            Select an artifact to inspect its versions.
          </div>
        )}
      </section>
    </div>
  );
}
