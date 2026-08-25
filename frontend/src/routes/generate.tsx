import { zodResolver } from "@hookform/resolvers/zod";
import {
  ArrowDown,
  ArrowUp,
  CircleAlert,
  Clock3,
  Database,
  LoaderCircle,
  Minus,
  Plus,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Controller,
  type FieldError,
  type FieldPath,
  useForm,
  useWatch,
} from "react-hook-form";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";

import { ApiError } from "@/api/errors";
import { DateTime } from "@/components/shared/date-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useCompetitionDetail } from "@/features/competitions/queries";
import {
  clearGenerationDraft,
  createGenerationFormDefaults,
  generationDraftSchema,
  GENERATION_DRAFT_VERSION,
  GENERATION_WEEK_OPTIONS,
  generationFormSchema,
  loadGenerationDraft,
  mapGenerationFormToSubmitBody,
  saveGenerationDraft,
  type GenerationFormValues,
} from "@/features/generations/draft";
import { useSubmitGeneration } from "@/features/generations/queries";
import type { ModelCatalogItem } from "@/features/models/api";
import { useModelCatalog } from "@/features/models/queries";
import { useRosterMappings } from "@/features/roster-mappings/queries";
import { useSeasonDetail, useSeasonList } from "@/features/seasons/queries";
import { cn } from "@/lib/utils";

const seasonListParameters = { limit: 200, offset: 0 } as const;
const selectClassName =
  "flex h-9 w-full rounded-md border border-border bg-background px-3 text-sm shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";
const textareaClassName =
  "min-h-28 w-full resize-y rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

function modelOptionLabel(model: ModelCatalogItem): string {
  const displayName = model.display_name.trim() || model.model;
  const provider = model.provider?.trim() ?? "provider unavailable";
  const identity =
    displayName === model.model
      ? model.model
      : `${displayName} (${model.model})`;
  const configuration = model.is_default ? "default" : "configured";
  const reasoning = model.supports_reasoning
    ? "reasoning supported"
    : "reasoning not supported";
  return `${identity} · ${provider} · ${configuration} · ${reasoning}`;
}

function FieldMessage({
  id,
  error,
}: {
  id?: string;
  error?: FieldError;
}): React.JSX.Element | null {
  if (!error?.message) return null;
  return (
    <p id={id} className="mt-1 text-xs text-destructive">
      {error.message}
    </p>
  );
}

const serverFieldPaths: Readonly<
  Record<string, FieldPath<GenerationFormValues>>
> = {
  competition_season_id: "competitionSeasonId",
  kind: "mode",
  request_text: "requestText",
  week_start: "weekStart",
  week_end: "weekEnd",
  requested_primary_model: "requestedPrimaryModel",
  "settings.report.voice": "report.voice",
  "settings.report.length_target": "report.lengthTarget",
  "settings.model.fallback_models": "model.fallbackModels",
  "settings.model.retry.max_retries": "model.retry.maxRetries",
  "settings.model.retry.base_delay_seconds": "model.retry.baseDelaySeconds",
  "settings.model.retry.max_delay_seconds": "model.retry.maxDelaySeconds",
  "settings.runner.max_turns": "runner.maxTurns",
  "settings.runner.procedure_history_mode": "runner.procedureHistoryMode",
};

function Section({
  number,
  title,
  description,
  children,
}: {
  number: string;
  title: string;
  description: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <section className="rounded-lg border border-border bg-card p-5 sm:p-6">
      <div className="flex gap-3">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
          {number}
        </span>
        <div>
          <h2 className="font-editorial text-2xl font-semibold">{title}</h2>
          <p className="mt-1 text-sm leading-6 text-muted-foreground">
            {description}
          </p>
        </div>
      </div>
      <div className="mt-6">{children}</div>
    </section>
  );
}

function StringListEditor({
  value,
  onChange,
  placeholder,
  label,
}: {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder: string;
  label: string;
}): React.JSX.Element {
  const [draft, setDraft] = useState("");

  function addValue(): void {
    const next = draft.trim();
    if (!next) return;
    onChange([...value, next]);
    setDraft("");
  }

  return (
    <div>
      <div className="flex gap-2">
        <Input
          value={draft}
          placeholder={placeholder}
          aria-label={label}
          onChange={(event) => {
            setDraft(event.target.value);
          }}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            addValue();
          }}
        />
        <Button type="button" variant="outline" onClick={addValue}>
          <Plus className="size-4" aria-hidden="true" />
          Add
        </Button>
      </div>
      {value.length > 0 ? (
        <ul
          className="mt-3 flex flex-wrap gap-2"
          aria-label={`${label} values`}
        >
          {value.map((item, index) => (
            <li
              key={`${item}-${String(index)}`}
              className="flex items-center gap-1 rounded-full border border-border bg-muted px-3 py-1 text-xs"
            >
              <span>{item}</span>
              <button
                type="button"
                className="rounded-full p-0.5 text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
                aria-label={`Remove ${item}`}
                onClick={() => {
                  onChange(value.filter((_, itemIndex) => itemIndex !== index));
                }}
              >
                <Minus className="size-3" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ToneControl({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}): React.JSX.Element {
  return (
    <label className="block text-sm font-medium">
      <span className="flex items-center justify-between">
        {label}
        <span className="text-xs text-muted-foreground">{value} / 3</span>
      </span>
      <input
        type="range"
        min={0}
        max={3}
        step={1}
        value={value}
        className="mt-2 w-full accent-[var(--primary)]"
        onChange={(event) => {
          onChange(Number(event.target.value));
        }}
      />
    </label>
  );
}

function PageSkeleton(): React.JSX.Element {
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-5 py-10 sm:px-8 sm:py-14">
      <Skeleton className="h-12 w-72" />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-5">
          <Skeleton className="h-72 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
        <Skeleton className="h-96 w-full" />
      </div>
    </div>
  );
}

export function Component(): React.JSX.Element {
  const { competitionId } = useParams();
  const navigate = useNavigate();
  const [searchParameters, setSearchParameters] = useSearchParams();
  const resolvedCompetitionId = competitionId ?? "";
  const competitionQuery = useCompetitionDetail(competitionId);
  const seasonsQuery = useSeasonList(competitionId, seasonListParameters);
  const modelsQuery = useModelCatalog();
  const submitGeneration = useSubmitGeneration(resolvedCompetitionId);
  const storedDefaults = useMemo(
    () =>
      competitionId
        ? (loadGenerationDraft(competitionId) ?? createGenerationFormDefaults())
        : createGenerationFormDefaults(),
    [competitionId],
  );
  const form = useForm<GenerationFormValues>({
    resolver: zodResolver(generationFormSchema),
    defaultValues: storedDefaults,
    mode: "onBlur",
  });
  const selectedSeasonId = useWatch({
    control: form.control,
    name: "competitionSeasonId",
  });
  const selectedMode = useWatch({ control: form.control, name: "mode" });
  const selectedPrimaryModel = useWatch({
    control: form.control,
    name: "requestedPrimaryModel",
  });
  const fallbackModels = useWatch({
    control: form.control,
    name: "model.fallbackModels",
  });
  const draftValues = useWatch({ control: form.control });
  const seasonDetailQuery = useSeasonDetail(
    competitionId,
    selectedSeasonId || undefined,
  );
  const mappingsQuery = useRosterMappings(
    competitionId,
    selectedSeasonId || undefined,
  );

  const seasons = useMemo(
    () => seasonsQuery.data?.page.items ?? [],
    [seasonsQuery.data],
  );
  const latestSeason = seasons.reduce<(typeof seasons)[number] | undefined>(
    (latest, candidate) =>
      !latest ||
      candidate.season.sequence_number > latest.season.sequence_number
        ? candidate
        : latest,
    undefined,
  );
  const selectedSeason = seasons.find(
    ({ season }) => season.id === selectedSeasonId,
  );
  const modelOptions = useMemo(
    () => modelsQuery.data?.models ?? [],
    [modelsQuery.data],
  );
  const validModelIds = useMemo(
    () => new Set(modelOptions.map((model) => model.model)),
    [modelOptions],
  );
  const selectedModel = modelOptions.find(
    (model) => model.model === selectedPrimaryModel,
  );
  const modelSelectionValid =
    validModelIds.has(selectedPrimaryModel) &&
    fallbackModels.every(
      (model) => model !== selectedPrimaryModel && validModelIds.has(model),
    );
  const lastSuccessfulRefresh =
    seasonDetailQuery.data?.summary.latest_successful_refresh_at ?? null;
  const mappingStatus = mappingsQuery.data?.mapping.status;
  const hasNormalizedData = seasonDetailQuery.data?.normalized_overview != null;
  const readyToGenerate =
    Boolean(selectedSeason) &&
    Boolean(lastSuccessfulRefresh) &&
    hasNormalizedData &&
    mappingStatus === "ready" &&
    !competitionQuery.data?.competition.archived_at;

  useEffect(() => {
    if (!competitionId) return;
    const parsed = generationDraftSchema.safeParse({
      version: GENERATION_DRAFT_VERSION,
      values: draftValues,
    });
    if (parsed.success) {
      saveGenerationDraft(competitionId, parsed.data.values);
    }
  }, [competitionId, draftValues]);

  useEffect(() => {
    if (seasons.length === 0) return;
    const requestedSeasonId = searchParameters.get("season");
    const requestedSeason = seasons.find(
      ({ season }) => season.id === requestedSeasonId,
    );
    const currentSeason = seasons.find(
      ({ season }) => season.id === form.getValues("competitionSeasonId"),
    );
    const nextSeason = requestedSeason ?? currentSeason ?? latestSeason;
    if (!nextSeason) return;
    if (form.getValues("competitionSeasonId") !== nextSeason.season.id) {
      form.setValue("competitionSeasonId", nextSeason.season.id);
    }
    if (requestedSeasonId !== nextSeason.season.id) {
      const next = new URLSearchParams(searchParameters);
      next.set("season", nextSeason.season.id);
      setSearchParameters(next, { replace: true });
    }
  }, [form, latestSeason, searchParameters, seasons, setSearchParameters]);

  useEffect(() => {
    const defaultModel =
      modelOptions.find((model) => model.is_default) ?? modelOptions[0];
    if (!defaultModel) return;
    const currentPrimary = form.getValues("requestedPrimaryModel");
    const nextPrimary = validModelIds.has(currentPrimary)
      ? currentPrimary
      : defaultModel.model;
    if (currentPrimary !== nextPrimary) {
      form.setValue("requestedPrimaryModel", nextPrimary, {
        shouldValidate: true,
      });
    }
    const currentFallbacks = form.getValues("model.fallbackModels");
    const nextFallbacks = currentFallbacks.filter(
      (model) => model !== nextPrimary && validModelIds.has(model),
    );
    if (nextFallbacks.length !== currentFallbacks.length) {
      form.setValue("model.fallbackModels", nextFallbacks, {
        shouldValidate: true,
      });
    }
  }, [form, modelOptions, validModelIds]);

  useEffect(() => {
    if (
      !selectedPrimaryModel ||
      !fallbackModels.includes(selectedPrimaryModel)
    ) {
      return;
    }
    form.setValue(
      "model.fallbackModels",
      fallbackModels.filter((model) => model !== selectedPrimaryModel),
      { shouldDirty: true, shouldValidate: true },
    );
  }, [fallbackModels, form, selectedPrimaryModel]);

  if (competitionQuery.isPending || seasonsQuery.isPending) {
    return <PageSkeleton />;
  }

  if (competitionQuery.isError || seasonsQuery.isError || !competitionId) {
    const error = competitionQuery.error ?? seasonsQuery.error;
    return (
      <div className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
        <CircleAlert className="size-8 text-destructive" aria-hidden="true" />
        <h1 className="mt-4 font-editorial text-3xl font-semibold">
          Generation setup unavailable
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          {error instanceof ApiError
            ? error.message
            : "The selected league and seasons could not be loaded."}
        </p>
        <Button
          className="mt-6"
          variant="outline"
          onClick={() =>
            void Promise.all([
              competitionQuery.refetch(),
              seasonsQuery.refetch(),
            ])
          }
        >
          Try again
        </Button>
      </div>
    );
  }

  const competition = competitionQuery.data.competition;

  if (seasons.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16 text-center sm:px-8">
        <Database
          className="mx-auto size-9 text-muted-foreground"
          aria-hidden="true"
        />
        <p className="mt-5 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Reporter assignment
        </p>
        <h1 className="mt-3 font-editorial text-4xl font-semibold">
          Add a season before generating
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-sm leading-6 text-muted-foreground">
          A generation needs an attached Sleeper season, refreshed source data,
          and complete team identity mappings.
        </p>
        <Link
          className="mt-7 inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground outline-none hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-ring"
          to={`/competitions/${competitionId}`}
        >
          Open league setup
        </Link>
      </div>
    );
  }

  function selectSeason(seasonId: string): void {
    form.setValue("competitionSeasonId", seasonId, {
      shouldDirty: true,
      shouldValidate: true,
    });
    const next = new URLSearchParams(searchParameters);
    next.set("season", seasonId);
    setSearchParameters(next);
  }

  const submit = form.handleSubmit(async (values) => {
    if (!readyToGenerate) {
      form.setError("root.server", {
        message: "Finish the selected season's data setup before generating.",
      });
      return;
    }
    if (!modelSelectionValid) {
      form.setError("requestedPrimaryModel", {
        message: "Choose models from the current configured catalog.",
      });
      return;
    }
    form.clearErrors("root.server");
    try {
      const response = await submitGeneration.mutateAsync(
        mapGenerationFormToSubmitBody(values),
      );
      clearGenerationDraft(competitionId);
      toast.success("Generation queued");
      await navigate(
        `/competitions/${competitionId}/generations/${response.generation.id}`,
      );
    } catch (error) {
      if (error instanceof ApiError) {
        for (const [wirePath, messages] of Object.entries(error.fieldErrors)) {
          const fieldPath = serverFieldPaths[wirePath];
          if (!fieldPath || messages.length === 0) continue;
          form.setError(fieldPath, {
            type: "server",
            message: messages.join(" "),
          });
        }
      }
      form.setError("root.server", {
        message:
          error instanceof ApiError
            ? error.message
            : "The generation could not be submitted.",
      });
    }
  });

  const selectableFallbacks = modelOptions.filter(
    (model) =>
      model.model !== selectedPrimaryModel &&
      !fallbackModels.includes(model.model),
  );

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          Reporter assignment
        </p>
        <h1 className="mt-3 font-editorial text-4xl font-semibold tracking-tight sm:text-5xl">
          Generate an article
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
          Configure a reproducible reporter run for {competition.display_name}.
          Submission creates a durable run record immediately.
        </p>
      </header>

      <form
        className="mt-9 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]"
        onSubmit={(event) => void submit(event)}
      >
        <div className="space-y-5">
          <Section
            number="1"
            title="Scope"
            description="Choose the factual boundary and whether memory may change."
          >
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Label htmlFor="generation-season">Season</Label>
                <select
                  id="generation-season"
                  className={cn(selectClassName, "mt-2")}
                  value={selectedSeasonId}
                  aria-invalid={Boolean(
                    form.formState.errors.competitionSeasonId,
                  )}
                  aria-describedby="generation-season-error"
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
                <FieldMessage
                  id="generation-season-error"
                  error={form.formState.errors.competitionSeasonId}
                />
              </div>
              <div>
                <Label htmlFor="week-start">Start week</Label>
                <select
                  id="week-start"
                  className={cn(selectClassName, "mt-2")}
                  aria-invalid={Boolean(form.formState.errors.weekStart)}
                  aria-describedby="week-start-error"
                  {...form.register("weekStart", { valueAsNumber: true })}
                >
                  {GENERATION_WEEK_OPTIONS.map((week) => (
                    <option key={week} value={week}>
                      Week {week}
                    </option>
                  ))}
                </select>
                <FieldMessage
                  id="week-start-error"
                  error={form.formState.errors.weekStart}
                />
              </div>
              <div>
                <Label htmlFor="week-end">End week</Label>
                <select
                  id="week-end"
                  className={cn(selectClassName, "mt-2")}
                  aria-invalid={Boolean(form.formState.errors.weekEnd)}
                  aria-describedby="week-end-error"
                  {...form.register("weekEnd", { valueAsNumber: true })}
                >
                  {GENERATION_WEEK_OPTIONS.map((week) => (
                    <option key={week} value={week}>
                      Week {week}
                    </option>
                  ))}
                </select>
                <FieldMessage
                  id="week-end-error"
                  error={form.formState.errors.weekEnd}
                />
              </div>
            </div>

            <fieldset className="mt-6">
              <legend className="text-sm font-medium">Generation mode</legend>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <label
                  className={cn(
                    "rounded-md border p-4",
                    selectedMode === "live"
                      ? "border-primary bg-accent/45"
                      : "border-border",
                  )}
                >
                  <span className="flex items-center gap-2 font-medium">
                    <input
                      type="radio"
                      value="live"
                      {...form.register("mode")}
                    />
                    Live
                  </span>
                  <span className="mt-2 block text-xs leading-5 text-muted-foreground">
                    Uses canonical reporter memory and may write memory on
                    success.
                  </span>
                </label>
                <label
                  className={cn(
                    "rounded-md border p-4",
                    selectedMode === "backtest"
                      ? "border-primary bg-accent/45"
                      : "border-border",
                  )}
                >
                  <span className="flex items-center gap-2 font-medium">
                    <input
                      type="radio"
                      value="backtest"
                      {...form.register("mode")}
                    />
                    Historical backtest
                  </span>
                  <span className="mt-2 block text-xs leading-5 text-muted-foreground">
                    Pins historical data and memory without canonical memory
                    writes.
                  </span>
                </label>
              </div>
              {selectedMode === "live" ? (
                <p className="mt-2 text-xs text-muted-foreground">
                  Live runs append to current canonical memory; they do not
                  rewind it. For a clean historical rebuild, start with empty
                  memory and run weeks in chronological order.
                </p>
              ) : null}
            </fieldset>
          </Section>

          <Section
            number="2"
            title="Assignment"
            description="Tell the reporter what to cover and which angles matter."
          >
            <Label htmlFor="request-text">Article request</Label>
            <textarea
              id="request-text"
              className={cn(textareaClassName, "mt-2")}
              placeholder="Write a sharp weekly recap focused on the playoff race…"
              aria-invalid={Boolean(form.formState.errors.requestText)}
              aria-describedby="request-text-error"
              {...form.register("requestText")}
            />
            <FieldMessage
              id="request-text-error"
              error={form.formState.errors.requestText}
            />
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <div>
                <Label>Focus teams</Label>
                <Controller
                  control={form.control}
                  name="report.focusTeams"
                  render={({ field }) => (
                    <div className="mt-2">
                      <StringListEditor
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Team name"
                        label="Focus team"
                      />
                    </div>
                  )}
                />
              </div>
              <div>
                <Label>Focus topics</Label>
                <Controller
                  control={form.control}
                  name="report.focusHints"
                  render={({ field }) => (
                    <div className="mt-2">
                      <StringListEditor
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Playoff race"
                        label="Focus topic"
                      />
                    </div>
                  )}
                />
              </div>
              <div className="sm:col-span-2">
                <Label>Topics to avoid</Label>
                <Controller
                  control={form.control}
                  name="report.avoidTopics"
                  render={({ field }) => (
                    <div className="mt-2">
                      <StringListEditor
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Trade rumors"
                        label="Topic to avoid"
                      />
                    </div>
                  )}
                />
              </div>
            </div>
          </Section>

          <Section
            number="3"
            title="Voice"
            description="Shape the editorial voice without changing the underlying facts."
          >
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <Label htmlFor="voice">Reporter voice</Label>
                <Input
                  id="voice"
                  className="mt-2"
                  aria-invalid={Boolean(form.formState.errors.report?.voice)}
                  aria-describedby="voice-error"
                  {...form.register("report.voice")}
                />
                <FieldMessage
                  id="voice-error"
                  error={form.formState.errors.report?.voice}
                />
              </div>
              <div>
                <Label htmlFor="length-target">Target words</Label>
                <Input
                  id="length-target"
                  type="number"
                  min={1}
                  className="mt-2"
                  aria-invalid={Boolean(
                    form.formState.errors.report?.lengthTarget,
                  )}
                  aria-describedby="length-target-error"
                  {...form.register("report.lengthTarget", {
                    valueAsNumber: true,
                  })}
                />
                <FieldMessage
                  id="length-target-error"
                  error={form.formState.errors.report?.lengthTarget}
                />
              </div>
              <div>
                <Label htmlFor="evidence-policy">Evidence policy</Label>
                <select
                  id="evidence-policy"
                  className={cn(selectClassName, "mt-2")}
                  {...form.register("report.evidencePolicy")}
                >
                  <option value="strict">Strict</option>
                  <option value="standard">Standard</option>
                  <option value="relaxed">Relaxed</option>
                </select>
              </div>
              <div>
                <Label htmlFor="profanity-policy">Profanity</Label>
                <select
                  id="profanity-policy"
                  className={cn(selectClassName, "mt-2")}
                  {...form.register("report.profanityPolicy")}
                >
                  <option value="none">None</option>
                  <option value="mild">Mild</option>
                  <option value="unrestricted">Unrestricted</option>
                </select>
              </div>
              <div className="grid gap-4 rounded-md border border-border p-4 sm:col-span-2 sm:grid-cols-3">
                <Controller
                  control={form.control}
                  name="report.tone.snarkLevel"
                  render={({ field }) => (
                    <ToneControl
                      label="Snark"
                      value={field.value}
                      onChange={field.onChange}
                    />
                  )}
                />
                <Controller
                  control={form.control}
                  name="report.tone.hypeLevel"
                  render={({ field }) => (
                    <ToneControl
                      label="Hype"
                      value={field.value}
                      onChange={field.onChange}
                    />
                  )}
                />
                <Controller
                  control={form.control}
                  name="report.tone.seriousness"
                  render={({ field }) => (
                    <ToneControl
                      label="Seriousness"
                      value={field.value}
                      onChange={field.onChange}
                    />
                  )}
                />
              </div>
              <div>
                <Label>Favored teams</Label>
                <Controller
                  control={form.control}
                  name="report.bias.favoredTeams"
                  render={({ field }) => (
                    <div className="mt-2">
                      <StringListEditor
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Team name"
                        label="Favored team"
                      />
                    </div>
                  )}
                />
              </div>
              <div>
                <Label>Disfavored teams</Label>
                <Controller
                  control={form.control}
                  name="report.bias.disfavoredTeams"
                  render={({ field }) => (
                    <div className="mt-2">
                      <StringListEditor
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Team name"
                        label="Disfavored team"
                      />
                    </div>
                  )}
                />
              </div>
              <div className="sm:col-span-2">
                <Controller
                  control={form.control}
                  name="report.bias.intensity"
                  render={({ field }) => (
                    <ToneControl
                      label="Bias intensity"
                      value={field.value}
                      onChange={field.onChange}
                    />
                  )}
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  Bias changes framing only. It never changes facts or numbers.
                </p>
              </div>
            </div>
          </Section>

          <Section
            number="4"
            title="Models"
            description="Choose the primary model and an ordered, unique fallback chain."
          >
            {modelsQuery.isPending ? (
              <Skeleton className="h-24 w-full" />
            ) : modelsQuery.isError ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/5 p-4">
                <p className="text-sm text-destructive">
                  {modelsQuery.error instanceof ApiError
                    ? modelsQuery.error.message
                    : "The configured model catalog could not be loaded."}
                </p>
                <Button
                  type="button"
                  className="mt-3"
                  variant="outline"
                  onClick={() => void modelsQuery.refetch()}
                >
                  Retry model catalog
                </Button>
              </div>
            ) : (
              <>
                <Label htmlFor="primary-model">Primary model</Label>
                <select
                  id="primary-model"
                  className={cn(selectClassName, "mt-2")}
                  aria-invalid={Boolean(
                    form.formState.errors.requestedPrimaryModel,
                  )}
                  aria-describedby="primary-model-error"
                  {...form.register("requestedPrimaryModel")}
                >
                  <option value="">Select a configured model</option>
                  {modelOptions.map((model) => (
                    <option key={model.model} value={model.model}>
                      {modelOptionLabel(model)}
                    </option>
                  ))}
                </select>
                <FieldMessage
                  id="primary-model-error"
                  error={form.formState.errors.requestedPrimaryModel}
                />
                {selectedModel ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    {selectedModel.provider} · {selectedModel.model}
                    {selectedModel.supports_reasoning
                      ? " · reasoning supported"
                      : ""}
                  </p>
                ) : null}

                <div className="mt-6">
                  <Label htmlFor="fallback-model">Fallback order</Label>
                  <Controller
                    control={form.control}
                    name="model.fallbackModels"
                    render={({ field }) => (
                      <>
                        <div className="mt-2 flex gap-2">
                          <select
                            id="fallback-model"
                            className={selectClassName}
                            defaultValue=""
                          >
                            <option value="">Choose a fallback</option>
                            {selectableFallbacks.map((model) => (
                              <option key={model.model} value={model.model}>
                                {modelOptionLabel(model)}
                              </option>
                            ))}
                          </select>
                          <Button
                            type="button"
                            variant="outline"
                            onClick={(event) => {
                              const select = event.currentTarget
                                .previousElementSibling as HTMLSelectElement | null;
                              if (!select?.value) return;
                              field.onChange([...field.value, select.value]);
                              select.value = "";
                            }}
                          >
                            <Plus className="size-4" aria-hidden="true" /> Add
                          </Button>
                        </div>
                        {field.value.length > 0 ? (
                          <ol className="mt-3 space-y-2">
                            {field.value.map((modelId, index) => {
                              const model = modelOptions.find(
                                (item) => item.model === modelId,
                              );
                              return (
                                <li
                                  key={modelId}
                                  className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"
                                >
                                  <span className="flex size-6 items-center justify-center rounded-full bg-muted text-xs">
                                    {index + 1}
                                  </span>
                                  <span className="min-w-0 flex-1 truncate">
                                    {model?.display_name ?? modelId}
                                  </span>
                                  <Button
                                    type="button"
                                    size="icon"
                                    variant="ghost"
                                    disabled={index === 0}
                                    aria-label={`Move ${modelId} up`}
                                    onClick={() => {
                                      const next = [...field.value];
                                      const current = next[index];
                                      const previous = next[index - 1];
                                      if (!current || !previous) return;
                                      next[index - 1] = current;
                                      next[index] = previous;
                                      field.onChange(next);
                                    }}
                                  >
                                    <ArrowUp
                                      className="size-4"
                                      aria-hidden="true"
                                    />
                                  </Button>
                                  <Button
                                    type="button"
                                    size="icon"
                                    variant="ghost"
                                    disabled={index === field.value.length - 1}
                                    aria-label={`Move ${modelId} down`}
                                    onClick={() => {
                                      const next = [...field.value];
                                      const current = next[index];
                                      const following = next[index + 1];
                                      if (!current || !following) return;
                                      next[index] = following;
                                      next[index + 1] = current;
                                      field.onChange(next);
                                    }}
                                  >
                                    <ArrowDown
                                      className="size-4"
                                      aria-hidden="true"
                                    />
                                  </Button>
                                  <Button
                                    type="button"
                                    size="icon"
                                    variant="ghost"
                                    aria-label={`Remove ${modelId}`}
                                    onClick={() => {
                                      field.onChange(
                                        field.value.filter(
                                          (item) => item !== modelId,
                                        ),
                                      );
                                    }}
                                  >
                                    <Minus
                                      className="size-4"
                                      aria-hidden="true"
                                    />
                                  </Button>
                                </li>
                              );
                            })}
                          </ol>
                        ) : (
                          <p className="mt-3 text-xs text-muted-foreground">
                            No fallback models selected.
                          </p>
                        )}
                      </>
                    )}
                  />
                </div>
              </>
            )}
          </Section>

          <details className="rounded-lg border border-border bg-card p-5 sm:p-6">
            <summary className="cursor-pointer font-editorial text-xl font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring">
              Advanced execution
            </summary>
            <p className="mt-2 text-sm text-muted-foreground">
              Retry timing and runner limits. Defaults are appropriate for most
              runs.
            </p>
            <div className="mt-5 grid gap-5 sm:grid-cols-2">
              <div>
                <Label htmlFor="max-retries">Maximum retries</Label>
                <Input
                  id="max-retries"
                  type="number"
                  min={0}
                  className="mt-2"
                  aria-invalid={Boolean(
                    form.formState.errors.model?.retry?.maxRetries,
                  )}
                  aria-describedby="max-retries-error"
                  {...form.register("model.retry.maxRetries", {
                    valueAsNumber: true,
                  })}
                />
                <FieldMessage
                  id="max-retries-error"
                  error={form.formState.errors.model?.retry?.maxRetries}
                />
              </div>
              <div>
                <Label htmlFor="max-turns">Maximum turns</Label>
                <Input
                  id="max-turns"
                  type="number"
                  min={1}
                  className="mt-2"
                  aria-invalid={Boolean(form.formState.errors.runner?.maxTurns)}
                  aria-describedby="max-turns-error"
                  {...form.register("runner.maxTurns", {
                    valueAsNumber: true,
                  })}
                />
                <FieldMessage
                  id="max-turns-error"
                  error={form.formState.errors.runner?.maxTurns}
                />
              </div>
              <div>
                <Label htmlFor="base-delay">Base delay (seconds)</Label>
                <Input
                  id="base-delay"
                  type="number"
                  min={0.1}
                  step={0.1}
                  className="mt-2"
                  aria-invalid={Boolean(
                    form.formState.errors.model?.retry?.baseDelaySeconds,
                  )}
                  aria-describedby="base-delay-error"
                  {...form.register("model.retry.baseDelaySeconds", {
                    valueAsNumber: true,
                  })}
                />
                <FieldMessage
                  id="base-delay-error"
                  error={form.formState.errors.model?.retry?.baseDelaySeconds}
                />
              </div>
              <div>
                <Label htmlFor="max-delay">Maximum delay (seconds)</Label>
                <Input
                  id="max-delay"
                  type="number"
                  min={0.1}
                  step={0.1}
                  className="mt-2"
                  aria-invalid={Boolean(
                    form.formState.errors.model?.retry?.maxDelaySeconds,
                  )}
                  aria-describedby="max-delay-error"
                  {...form.register("model.retry.maxDelaySeconds", {
                    valueAsNumber: true,
                  })}
                />
                <FieldMessage
                  id="max-delay-error"
                  error={form.formState.errors.model?.retry?.maxDelaySeconds}
                />
              </div>
              <div className="sm:col-span-2">
                <Label htmlFor="procedure-history">Procedure history</Label>
                <select
                  id="procedure-history"
                  className={cn(selectClassName, "mt-2")}
                  {...form.register("runner.procedureHistoryMode")}
                >
                  <option value="replace">Replace each procedure view</option>
                  <option value="append">Append procedure history</option>
                </select>
              </div>
            </div>
          </details>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-24">
          <section className="rounded-lg border border-border bg-card p-5">
            <div className="flex items-center gap-2">
              <Sparkles
                className="size-4 text-muted-foreground"
                aria-hidden="true"
              />
              <h2 className="font-semibold">Run summary</h2>
            </div>
            <dl className="mt-5 space-y-4 text-sm">
              <div className="flex items-start justify-between gap-3">
                <dt className="text-muted-foreground">Season</dt>
                <dd className="text-right font-medium">
                  {selectedSeason?.season.season_year ?? "—"}
                </dd>
              </div>
              <div className="flex items-start justify-between gap-3 border-t border-border pt-4">
                <dt className="text-muted-foreground">Mode</dt>
                <dd>
                  <Badge variant="outline">
                    {selectedMode === "live" ? "Live" : "Backtest"}
                  </Badge>
                </dd>
              </div>
              <div className="flex items-start justify-between gap-3 border-t border-border pt-4">
                <dt className="text-muted-foreground">Model chain</dt>
                <dd className="text-right">
                  {selectedPrimaryModel
                    ? `${String(1 + fallbackModels.length)} model${fallbackModels.length === 0 ? "" : "s"}`
                    : "—"}
                </dd>
              </div>
            </dl>
          </section>

          <section className="rounded-lg border border-border bg-card p-5">
            <div className="flex items-center gap-2">
              <Clock3
                className="size-4 text-muted-foreground"
                aria-hidden="true"
              />
              <h2 className="font-semibold">Data readiness</h2>
            </div>
            {seasonDetailQuery.isPending || mappingsQuery.isPending ? (
              <Skeleton className="mt-4 h-20 w-full" />
            ) : seasonDetailQuery.isError || mappingsQuery.isError ? (
              <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/5 p-3">
                <p className="text-sm text-destructive">
                  Season readiness could not be loaded.
                </p>
                <Button
                  type="button"
                  className="mt-3"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    void Promise.all([
                      seasonDetailQuery.refetch(),
                      mappingsQuery.refetch(),
                    ]);
                  }}
                >
                  Retry readiness
                </Button>
              </div>
            ) : (
              <>
                <p
                  className={cn(
                    "mt-4 text-sm font-medium",
                    readyToGenerate ? "text-primary" : "text-destructive",
                  )}
                >
                  {competition.archived_at
                    ? "Archived league"
                    : !hasNormalizedData
                      ? "Sleeper data not loaded"
                      : mappingStatus !== "ready"
                        ? "Team identity setup required"
                        : !lastSuccessfulRefresh
                          ? "No successful refresh"
                          : "Ready to generate"}
                </p>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">
                  Last successful refresh:{" "}
                  <DateTime value={lastSuccessfulRefresh} />
                </p>
                {!readyToGenerate ? (
                  <Link
                    className="mt-4 inline-flex text-sm font-medium text-primary underline-offset-4 hover:underline"
                    to={`/competitions/${competitionId}?season=${selectedSeasonId}`}
                  >
                    Finish season setup
                  </Link>
                ) : null}
              </>
            )}
            <p className="mt-4 border-t border-border pt-4 text-xs leading-5 text-muted-foreground">
              Refresh and generation snapshots are separate. A same-day run may
              reuse an earlier ready daily snapshot; snapshot time is shown on
              the resulting run audit.
            </p>
          </section>

          {form.formState.errors.root?.server ? (
            <div
              className="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
              role="alert"
            >
              {form.formState.errors.root.server.message}
            </div>
          ) : null}

          <Button
            type="submit"
            className="w-full"
            disabled={
              !readyToGenerate ||
              modelsQuery.isError ||
              !modelSelectionValid ||
              submitGeneration.isPending
            }
          >
            {submitGeneration.isPending ? (
              <LoaderCircle
                className="size-4 animate-spin"
                aria-hidden="true"
              />
            ) : (
              <Sparkles className="size-4" aria-hidden="true" />
            )}
            {submitGeneration.isPending
              ? "Creating durable run…"
              : "Generate article"}
          </Button>
          <p
            className="text-center text-xs leading-5 text-muted-foreground"
            aria-live="polite"
          >
            The next page tracks pending, running, and terminal state. Reloading
            will not lose the run.
          </p>
        </aside>
      </form>
    </div>
  );
}
