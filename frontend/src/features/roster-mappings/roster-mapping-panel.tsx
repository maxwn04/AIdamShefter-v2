import { CheckCircle2, Link2, UsersRound } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/errors";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import type { ManualRefreshResponse } from "@/features/refreshes/api";
import { useManualRefresh } from "@/features/refreshes/queries";
import type {
  PutRosterMappingsBody,
  RosterMappingView,
} from "@/features/roster-mappings/api";
import {
  usePutRosterMappings,
  useRosterMappings,
} from "@/features/roster-mappings/queries";

interface DraftChoice {
  choice: string;
  newName: string;
}

function mergeMappingDrafts(
  mapping: RosterMappingView,
  current: Record<string, DraftChoice> = {},
): Record<string, DraftChoice> {
  return Object.fromEntries(
    mapping.rosters.map((roster) => {
      const previous = current[roster.sleeper_roster_id];
      if (roster.franchise_id) {
        return [
          roster.sleeper_roster_id,
          {
            choice: `existing:${roster.franchise_id}`,
            newName: roster.suggested_display_name,
          },
        ];
      }
      return [
        roster.sleeper_roster_id,
        previous ?? {
          choice: "",
          newName: roster.suggested_display_name,
        },
      ];
    }),
  );
}

interface RosterMappingPanelProps {
  competitionId: string;
  seasonId: string;
  seasonYear: number;
  requestedThroughWeek?: number | null;
  disabled?: boolean;
  onOutcome: (outcome: ManualRefreshResponse) => void;
}

export function RosterMappingPanel({
  competitionId,
  seasonId,
  seasonYear,
  requestedThroughWeek,
  disabled = false,
  onOutcome,
}: RosterMappingPanelProps): React.JSX.Element {
  const query = useRosterMappings(competitionId, seasonId);
  const [setupMapping, setSetupMapping] = useState<RosterMappingView>();

  if (query.isPending) {
    return (
      <div className="mt-5 h-24 animate-pulse rounded-lg border border-border bg-muted/50" />
    );
  }
  if (query.isError) {
    return (
      <div className="mt-5 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <p className="text-sm text-destructive">
          {query.error instanceof ApiError
            ? query.error.message
            : "Team identity readiness could not be loaded."}
        </p>
        <Button
          className="mt-3"
          size="sm"
          variant="outline"
          onClick={() => void query.refetch()}
        >
          Try again
        </Button>
      </div>
    );
  }

  const mapping = setupMapping ?? query.data.mapping;
  if (mapping.status === "ready") {
    return (
      <div className="mt-5 flex flex-col gap-3 rounded-lg border border-emerald-600/25 bg-emerald-500/5 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <CheckCircle2
            className="mt-0.5 size-5 text-emerald-700"
            aria-hidden="true"
          />
          <div>
            <p className="font-medium">Team identities ready</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {mapping.mapped_count} of {mapping.roster_count} teams are
              connected for this season.
            </p>
          </div>
        </div>
        <Badge variant="outline">Teams connected</Badge>
      </div>
    );
  }

  if (mapping.status === "awaiting_source") {
    return (
      <div className="mt-5 flex items-start gap-3 rounded-lg border border-border bg-muted/45 p-4">
        <UsersRound
          className="mt-0.5 size-5 text-muted-foreground"
          aria-hidden="true"
        />
        <div>
          <p className="font-medium">Team identities pending</p>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            Run a Sleeper refresh to discover this season&apos;s rosters. The
            first season is connected automatically; later seasons ask you to
            confirm team continuity.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-5 flex flex-col gap-4 rounded-lg border border-amber-600/30 bg-amber-500/5 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-start gap-3">
        <Link2 className="mt-0.5 size-5 text-amber-700" aria-hidden="true" />
        <div>
          <p className="font-medium">Team setup required</p>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            Confirm how {mapping.roster_count} Sleeper rosters continue the
            competition&apos;s teams before generating.
          </p>
        </div>
      </div>
      <RosterMappingSheet
        competitionId={competitionId}
        seasonId={seasonId}
        seasonYear={seasonYear}
        mapping={mapping}
        requestedThroughWeek={requestedThroughWeek}
        disabled={disabled}
        onReload={async () => {
          const result = await query.refetch();
          if (result.data) {
            setSetupMapping(result.data.mapping);
            return result.data.mapping;
          }
          return undefined;
        }}
        onOpenStateChange={(nextOpen) => {
          setSetupMapping(nextOpen ? mapping : undefined);
        }}
        onOutcome={onOutcome}
      />
    </div>
  );
}

function RosterMappingSheet({
  competitionId,
  seasonId,
  seasonYear,
  mapping,
  requestedThroughWeek,
  disabled,
  onReload,
  onOpenStateChange,
  onOutcome,
}: {
  competitionId: string;
  seasonId: string;
  seasonYear: number;
  mapping: RosterMappingView;
  requestedThroughWeek?: number | null;
  disabled: boolean;
  onReload: () => Promise<RosterMappingView | undefined>;
  onOpenStateChange: (open: boolean) => void;
  onOutcome: (outcome: ManualRefreshResponse) => void;
}): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, DraftChoice>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [mappingSaved, setMappingSaved] = useState(false);
  const [refreshNeedsRetry, setRefreshNeedsRetry] = useState(false);
  const mappingMutation = usePutRosterMappings(competitionId, seasonId);
  const refreshMutation = useManualRefresh(competitionId, seasonId);
  const pending = mappingMutation.isPending || refreshMutation.isPending;

  const selectedExisting = useMemo(
    () =>
      new Map(
        Object.entries(drafts).flatMap(([rosterId, draft]) =>
          draft.choice.startsWith("existing:")
            ? [[draft.choice.slice("existing:".length), rosterId] as const]
            : [],
        ),
      ),
    [drafts],
  );

  function handleOpenChange(nextOpen: boolean): void {
    if (pending && !nextOpen) return;
    setOpen(nextOpen);
    onOpenStateChange(nextOpen);
    if (nextOpen) {
      setDrafts(mergeMappingDrafts(mapping));
      mappingMutation.reset();
      refreshMutation.reset();
      setErrors({});
      setMappingSaved(false);
      setRefreshNeedsRetry(false);
    }
  }

  async function runRefresh(): Promise<void> {
    setRefreshNeedsRetry(false);
    try {
      const outcome = await refreshMutation.mutateAsync(
        requestedThroughWeek ?? undefined,
      );
      onOutcome(outcome);
      if (outcome.refresh.status === "succeeded") {
        toast.success("Team setup and refresh completed");
        handleOpenChange(false);
      } else if (outcome.refresh.status === "partial") {
        toast.warning("Teams saved; refresh completed partially");
        setRefreshNeedsRetry(true);
      } else {
        toast.error("Teams saved; refresh failed");
        setRefreshNeedsRetry(true);
      }
    } catch {
      // The mapping is durable; the retry action remains in the sheet.
      setRefreshNeedsRetry(true);
    }
  }

  async function submit(
    event: React.SyntheticEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    for (const roster of mapping.rosters) {
      const draft = drafts[roster.sleeper_roster_id];
      if (!draft?.choice) {
        nextErrors[roster.sleeper_roster_id] =
          "Choose an existing team or create a new one.";
      } else if (draft.choice === "new" && !draft.newName.trim()) {
        nextErrors[roster.sleeper_roster_id] = "Enter a new team name.";
      }
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    if (!mapping.source_api_request_id) return;

    const assignments: PutRosterMappingsBody["assignments"] =
      mapping.rosters.map((roster) => {
        const draft = drafts[roster.sleeper_roster_id];
        if (!draft)
          throw new Error("validated roster mapping draft is missing");
        if (draft.choice === "new") {
          return {
            sleeper_roster_id: roster.sleeper_roster_id,
            target: { kind: "new", display_name: draft.newName.trim() },
          };
        }
        return {
          sleeper_roster_id: roster.sleeper_roster_id,
          target: {
            kind: "existing",
            franchise_id: draft.choice.slice("existing:".length),
          },
        };
      });

    try {
      await mappingMutation.mutateAsync({
        source_api_request_id: mapping.source_api_request_id,
        assignments,
      });
      setMappingSaved(true);
      await runRefresh();
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.code === "roster_mapping_source_stale"
      ) {
        const refreshedMapping = await onReload();
        if (refreshedMapping) {
          setDrafts((current) => mergeMappingDrafts(refreshedMapping, current));
        }
      }
    }
  }

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetTrigger asChild>
        <Button disabled={disabled}>Set up teams</Button>
      </SheetTrigger>
      <SheetContent
        side="right"
        className="w-[min(42rem,96vw)] overflow-y-auto"
      >
        <SheetHeader>
          <SheetTitle>Connect {seasonYear} teams</SheetTitle>
          <SheetDescription>
            Sleeper names and owners are evidence only. Explicitly connect each
            roster to one existing team or create a new team.
          </SheetDescription>
        </SheetHeader>

        {mappingSaved ? (
          <div className="rounded-md border border-emerald-600/25 bg-emerald-500/5 p-4">
            <p className="font-medium">Team mappings are saved.</p>
            <p className="mt-1 text-sm text-muted-foreground">
              The full Sleeper refresh still needs to complete. Retrying will
              not reopen or change the saved mappings.
            </p>
            {refreshMutation.isPending ? (
              <p className="mt-4 text-sm" role="status" aria-live="polite">
                Refreshing Sleeper data…
              </p>
            ) : null}
            {refreshNeedsRetry || refreshMutation.error ? (
              <Button
                className="mt-4"
                variant="outline"
                disabled={refreshMutation.isPending}
                onClick={() => {
                  void runRefresh();
                }}
              >
                {refreshMutation.isPending ? "Refreshing…" : "Retry refresh"}
              </Button>
            ) : null}
          </div>
        ) : (
          <form onSubmit={(event) => void submit(event)} noValidate>
            <div className="space-y-5">
              {mapping.rosters.map((roster) => {
                const draft = drafts[roster.sleeper_roster_id] ?? {
                  choice: "",
                  newName: roster.suggested_display_name,
                };
                const immutable = roster.franchise_id !== null;
                return (
                  <fieldset
                    key={roster.sleeper_roster_id}
                    className="rounded-lg border border-border p-4"
                    disabled={pending || immutable}
                  >
                    <legend className="px-1 font-medium">
                      Sleeper roster {roster.sleeper_roster_id}
                    </legend>
                    <p className="mt-1 text-sm font-medium">
                      {roster.suggested_display_name}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {roster.managers.length > 0
                        ? roster.managers
                            .map(
                              (manager) =>
                                `${manager.display_name}${manager.role === "co_owner" ? " (co-owner)" : ""}`,
                            )
                            .join(", ")
                        : "No Sleeper owner is currently listed."}
                    </p>
                    <div className="mt-4 space-y-2">
                      <Label htmlFor={`mapping-${roster.sleeper_roster_id}`}>
                        Competition team
                      </Label>
                      <select
                        id={`mapping-${roster.sleeper_roster_id}`}
                        className="block h-10 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
                        value={draft.choice}
                        aria-invalid={
                          errors[roster.sleeper_roster_id] ? true : undefined
                        }
                        onChange={(event) => {
                          const choice = event.target.value;
                          setDrafts((current) => ({
                            ...current,
                            [roster.sleeper_roster_id]: { ...draft, choice },
                          }));
                          setErrors((current) => ({
                            ...current,
                            [roster.sleeper_roster_id]: "",
                          }));
                        }}
                      >
                        <option value="">Choose a team…</option>
                        <option value="new">Create a new team</option>
                        {mapping.franchise_options.map((franchise) => {
                          const selectedBy = selectedExisting.get(franchise.id);
                          return (
                            <option
                              key={franchise.id}
                              value={`existing:${franchise.id}`}
                              disabled={
                                selectedBy !== undefined &&
                                selectedBy !== roster.sleeper_roster_id
                              }
                            >
                              {franchise.display_name}
                            </option>
                          );
                        })}
                      </select>
                    </div>
                    {draft.choice === "new" ? (
                      <div className="mt-3 space-y-2">
                        <Label htmlFor={`new-team-${roster.sleeper_roster_id}`}>
                          New team name
                        </Label>
                        <Input
                          id={`new-team-${roster.sleeper_roster_id}`}
                          value={draft.newName}
                          onChange={(event) => {
                            setDrafts((current) => ({
                              ...current,
                              [roster.sleeper_roster_id]: {
                                ...draft,
                                newName: event.target.value,
                              },
                            }));
                          }}
                        />
                      </div>
                    ) : null}
                    {immutable ? (
                      <p className="mt-3 text-xs text-muted-foreground">
                        This roster is already connected and cannot be remapped.
                      </p>
                    ) : null}
                    {errors[roster.sleeper_roster_id] ? (
                      <p className="mt-3 text-sm text-destructive">
                        {errors[roster.sleeper_roster_id]}
                      </p>
                    ) : null}
                  </fieldset>
                );
              })}
            </div>

            {mappingMutation.error ? (
              <p
                className="mt-5 rounded-md bg-destructive/10 p-4 text-sm text-destructive"
                role="alert"
              >
                {mappingMutation.error instanceof ApiError
                  ? mappingMutation.error.message
                  : "The team mappings could not be saved."}
              </p>
            ) : null}

            <div className="mt-8 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="ghost"
                disabled={pending}
                onClick={() => {
                  handleOpenChange(false);
                }}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={pending}>
                {mappingMutation.isPending
                  ? "Saving teams…"
                  : refreshMutation.isPending
                    ? "Refreshing…"
                    : "Save teams and refresh"}
              </Button>
            </div>
          </form>
        )}
      </SheetContent>
    </Sheet>
  );
}
