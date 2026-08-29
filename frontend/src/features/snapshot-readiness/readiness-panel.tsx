import { CircleAlert, Clock3, LoaderCircle } from "lucide-react";
import { Link } from "react-router";

import { ApiError } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  SnapshotPreparationResponse,
  SnapshotReadinessResponse,
} from "@/features/snapshot-readiness/api";

interface SnapshotReadinessPanelProperties {
  competitionId: string;
  readiness: SnapshotReadinessResponse | undefined;
  readinessPending: boolean;
  readinessError: Error | null;
  preparation: SnapshotPreparationResponse | undefined;
  preparationPending: boolean;
  preparationError: Error | null;
  onRetry: () => void;
  onPrepare: () => void;
}

function seasonYears(readiness: SnapshotReadinessResponse): string {
  if (readiness.state.kind !== "ready") return "";
  return readiness.state.included_seasons
    .map((season) => String(season.season_year))
    .join(", ");
}

function mappingLink(competitionId: string, seasonId: string): string {
  return `/competitions/${competitionId}?season=${seasonId}`;
}

export function SnapshotReadinessPanel({
  competitionId,
  readiness,
  readinessPending,
  readinessError,
  preparation,
  preparationPending,
  preparationError,
  onRetry,
  onPrepare,
}: SnapshotReadinessPanelProperties): React.JSX.Element {
  const preparationMappingSeasonId =
    preparationError instanceof ApiError &&
    preparationError.code === "roster_identity_mapping_required"
      ? preparationError.competitionSeasonId
      : undefined;

  return (
    <section className="rounded-lg border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <Clock3 className="size-4 text-muted-foreground" aria-hidden="true" />
        <h2 className="font-semibold">Data readiness</h2>
      </div>

      {readinessPending ? (
        <div aria-label="Loading snapshot readiness">
          <Skeleton className="mt-4 h-24 w-full" />
        </div>
      ) : readinessError ? (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3">
          <p className="text-sm text-destructive">
            Snapshot readiness could not be loaded. Generation is blocked until
            the check succeeds.
          </p>
          <Button
            type="button"
            className="mt-3"
            size="sm"
            variant="outline"
            onClick={onRetry}
          >
            Retry readiness
          </Button>
        </div>
      ) : preparationMappingSeasonId ? (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3">
          <p className="text-sm font-medium text-destructive">
            Preparation found a historical team identity blocker.
          </p>
          <Link
            className="mt-3 inline-flex text-sm font-medium text-primary underline-offset-4 hover:underline"
            to={mappingLink(competitionId, preparationMappingSeasonId)}
          >
            Map the affected season
          </Link>
        </div>
      ) : readiness?.state.kind === "ready" ? (
        <div className="mt-4">
          <p className="text-sm font-medium text-primary">Ready to generate</p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            Frozen coverage: {seasonYears(readiness)}. Revision{" "}
            {readiness.state.input_revision.slice(0, 12)}…
          </p>
        </div>
      ) : readiness?.state.kind === "refresh_required" ? (
        <div className="mt-4 rounded-md border border-amber-500/30 bg-amber-500/5 p-3">
          <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
            {readiness.state.season.season_year} needs a{" "}
            {readiness.state.reason} refresh through week{" "}
            {readiness.state.season.through_week}.
          </p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">
            You may generate now; generation will run the same bounded automatic
            preparation.
          </p>
          <Button
            type="button"
            className="mt-3"
            size="sm"
            variant="outline"
            disabled={preparationPending}
            onClick={onPrepare}
          >
            {preparationPending ? (
              <LoaderCircle
                className="size-4 animate-spin"
                aria-hidden="true"
              />
            ) : null}
            {preparationPending ? "Preparing…" : "Prepare now"}
          </Button>
        </div>
      ) : readiness?.state.kind === "roster_mapping_required" ? (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3">
          <p className="text-sm font-medium text-destructive">
            {readiness.state.season.season_year} needs team identity mapping for{" "}
            {readiness.state.sleeper_roster_ids.length} roster
            {readiness.state.sleeper_roster_ids.length === 1 ? "" : "s"}.
          </p>
          <Link
            className="mt-3 inline-flex text-sm font-medium text-primary underline-offset-4 hover:underline"
            to={mappingLink(
              competitionId,
              readiness.state.season.competition_season_id,
            )}
          >
            Map the affected season
          </Link>
        </div>
      ) : (
        <div className="mt-4 flex gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <p>Snapshot readiness is unknown. Generation is blocked.</p>
        </div>
      )}

      {preparationError && !preparationMappingSeasonId ? (
        <p className="mt-3 text-xs leading-5 text-destructive" role="alert">
          {preparationError instanceof ApiError
            ? preparationError.message
            : "Snapshot preparation failed. Retry readiness before continuing."}
        </p>
      ) : null}
      {preparation ? (
        <p className="mt-3 text-xs leading-5 text-primary" aria-live="polite">
          Prepared snapshot {preparation.snapshot.id.slice(0, 8)} with{" "}
          {preparation.snapshot.included_seasons.length} season
          {preparation.snapshot.included_seasons.length === 1
            ? ""
            : "s"} and {preparation.refresh_receipts.length} refresh receipt
          {preparation.refresh_receipts.length === 1 ? "" : "s"}.
        </p>
      ) : null}
      <p className="mt-4 border-t border-border pt-4 text-xs leading-5 text-muted-foreground">
        Version-3 snapshots are reused only when factual inputs have the same
        revision. Changed facts produce a new snapshot revision.
      </p>
    </section>
  );
}
