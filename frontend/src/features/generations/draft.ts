import { z } from "zod";

import type { SubmitGenerationBody } from "@/features/generations/api";

export const GENERATION_DRAFT_VERSION = 1 as const;
export const GENERATION_WEEK_OPTIONS = Array.from(
  { length: 18 },
  (_, index) => index + 1,
) as readonly number[];

const trimmedListItemSchema = z
  .string()
  .trim()
  .min(1, "Remove empty list items.");
const humanReadableListSchema = z.array(trimmedListItemSchema);
const controlLevelSchema = z.coerce
  .number<number>()
  .int()
  .min(0, "Use a level from 0 through 3.")
  .max(3, "Use a level from 0 through 3.");
const weekSchema = z.coerce
  .number<number>()
  .int("Use a whole week from 1 through 18.")
  .min(1, "Week must be from 1 through 18.")
  .max(18, "Week must be from 1 through 18.");

const generationDraftValuesSchema = z
  .object({
    competitionSeasonId: z.string(),
    mode: z.enum(["live", "backtest"]),
    requestText: z.string(),
    weekStart: weekSchema,
    weekEnd: weekSchema,
    requestedPrimaryModel: z.string(),
    report: z.object({
      focusHints: humanReadableListSchema,
      avoidTopics: humanReadableListSchema,
      focusTeams: humanReadableListSchema,
      voice: z.string(),
      tone: z.object({
        snarkLevel: controlLevelSchema,
        hypeLevel: controlLevelSchema,
        seriousness: controlLevelSchema,
      }),
      profanityPolicy: z.enum(["none", "mild", "unrestricted"]),
      bias: z.object({
        favoredTeams: humanReadableListSchema,
        disfavoredTeams: humanReadableListSchema,
        intensity: controlLevelSchema,
      }),
      lengthTarget: z.coerce
        .number<number>()
        .int("Length target must be a whole number.")
        .min(1, "Length target must be at least 1."),
      evidencePolicy: z.enum(["strict", "standard", "relaxed"]),
    }),
    model: z.object({
      fallbackModels: humanReadableListSchema,
      retry: z.object({
        maxRetries: z.coerce
          .number<number>()
          .int("Retries must be a whole number.")
          .min(0, "Retries cannot be negative."),
        baseDelaySeconds: z.coerce
          .number<number>()
          .positive("Base delay must be greater than 0."),
        maxDelaySeconds: z.coerce
          .number<number>()
          .positive("Maximum delay must be greater than 0."),
      }),
    }),
    runner: z.object({
      maxTurns: z.coerce
        .number<number>()
        .int("Maximum turns must be a whole number.")
        .min(1, "Maximum turns must be at least 1."),
      procedureHistoryMode: z.enum(["replace", "append"]),
    }),
  })
  .superRefine((values, context) => {
    if (values.weekStart > values.weekEnd) {
      context.addIssue({
        code: "custom",
        message: "Start week cannot be after end week.",
        path: ["weekEnd"],
      });
    }

    if (
      values.model.retry.maxDelaySeconds < values.model.retry.baseDelaySeconds
    ) {
      context.addIssue({
        code: "custom",
        message: "Maximum delay must be at least the base delay.",
        path: ["model", "retry", "maxDelaySeconds"],
      });
    }
  });

export const generationFormSchema = generationDraftValuesSchema.superRefine(
  (values, context) => {
    if (values.competitionSeasonId.trim().length === 0) {
      context.addIssue({
        code: "custom",
        message: "Select a season.",
        path: ["competitionSeasonId"],
      });
    }
    if (values.requestText.trim().length === 0) {
      context.addIssue({
        code: "custom",
        message: "Describe the reporter assignment.",
        path: ["requestText"],
      });
    }
    if (values.requestedPrimaryModel.trim().length === 0) {
      context.addIssue({
        code: "custom",
        message: "Select a primary model.",
        path: ["requestedPrimaryModel"],
      });
    }
    if (values.report.voice.trim().length === 0) {
      context.addIssue({
        code: "custom",
        message: "Enter a reporter voice.",
        path: ["report", "voice"],
      });
    }

    const modelChain = [
      values.requestedPrimaryModel.trim(),
      ...values.model.fallbackModels,
    ];
    if (new Set(modelChain).size !== modelChain.length) {
      context.addIssue({
        code: "custom",
        message: "The primary and fallback models must all be unique.",
        path: ["model", "fallbackModels"],
      });
    }
  },
);

export type GenerationFormValues = z.output<typeof generationFormSchema>;

export const generationDraftSchema = z.object({
  version: z.literal(GENERATION_DRAFT_VERSION),
  values: generationDraftValuesSchema,
});
export type GenerationDraft = z.output<typeof generationDraftSchema>;

export function createGenerationFormDefaults(
  primaryModel = "",
  competitionSeasonId = "",
): GenerationFormValues {
  return {
    competitionSeasonId,
    mode: "live",
    requestText: "",
    weekStart: 1,
    weekEnd: 1,
    requestedPrimaryModel: primaryModel,
    report: {
      focusHints: [],
      avoidTopics: [],
      focusTeams: [],
      voice: "sports columnist",
      tone: { snarkLevel: 1, hypeLevel: 1, seriousness: 1 },
      profanityPolicy: "none",
      bias: { favoredTeams: [], disfavoredTeams: [], intensity: 1 },
      lengthTarget: 1000,
      evidencePolicy: "standard",
    },
    model: {
      fallbackModels: [],
      retry: { maxRetries: 3, baseDelaySeconds: 1, maxDelaySeconds: 30 },
    },
    runner: { maxTurns: 60, procedureHistoryMode: "replace" },
  };
}

export function mapGenerationFormToSubmitBody(
  unparsedValues: GenerationFormValues,
): SubmitGenerationBody {
  const values = generationFormSchema.parse(unparsedValues);
  const hasBias =
    values.report.bias.favoredTeams.length > 0 ||
    values.report.bias.disfavoredTeams.length > 0;

  return {
    competition_season_id: values.competitionSeasonId.trim(),
    kind: values.mode,
    request_text: values.requestText.trim(),
    week_start: values.weekStart,
    week_end: values.weekEnd,
    requested_primary_model: values.requestedPrimaryModel.trim(),
    settings: {
      report: {
        focus_hints: values.report.focusHints,
        avoid_topics: values.report.avoidTopics,
        focus_teams: values.report.focusTeams,
        voice: values.report.voice.trim(),
        tone: {
          snark_level: values.report.tone.snarkLevel,
          hype_level: values.report.tone.hypeLevel,
          seriousness: values.report.tone.seriousness,
        },
        profanity_policy: values.report.profanityPolicy,
        ...(hasBias
          ? {
              bias: {
                favored_teams: values.report.bias.favoredTeams,
                disfavored_teams: values.report.bias.disfavoredTeams,
                intensity: values.report.bias.intensity,
              },
            }
          : {}),
        length_target: values.report.lengthTarget,
        evidence_policy: values.report.evidencePolicy,
      },
      model: {
        fallback_models: values.model.fallbackModels,
        retry: {
          max_retries: values.model.retry.maxRetries,
          base_delay_seconds: values.model.retry.baseDelaySeconds,
          max_delay_seconds: values.model.retry.maxDelaySeconds,
        },
      },
      runner: {
        max_turns: values.runner.maxTurns,
        procedure_history_mode: values.runner.procedureHistoryMode,
      },
    },
  };
}

function draftStorageKey(competitionId: string): string {
  return `aidam:generation-draft:${String(GENERATION_DRAFT_VERSION)}:${competitionId}`;
}

function browserStorage(): Storage | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

export function loadGenerationDraft(
  competitionId: string,
  storage: Storage | undefined = browserStorage(),
): GenerationFormValues | undefined {
  if (!storage) return undefined;
  try {
    const serialized = storage.getItem(draftStorageKey(competitionId));
    if (!serialized) return undefined;
    const parsed = generationDraftSchema.safeParse(
      JSON.parse(serialized) as unknown,
    );
    return parsed.success ? parsed.data.values : undefined;
  } catch {
    return undefined;
  }
}

export function saveGenerationDraft(
  competitionId: string,
  values: GenerationFormValues,
  storage: Storage | undefined = browserStorage(),
): void {
  if (!storage) return;
  const parsed = generationDraftValuesSchema.safeParse(values);
  if (!parsed.success) return;
  try {
    storage.setItem(
      draftStorageKey(competitionId),
      JSON.stringify({
        version: GENERATION_DRAFT_VERSION,
        values: parsed.data,
      }),
    );
  } catch {
    // Draft persistence is best-effort; form submission remains available.
  }
}

export function clearGenerationDraft(
  competitionId: string,
  storage: Storage | undefined = browserStorage(),
): void {
  if (!storage) return;
  try {
    storage.removeItem(draftStorageKey(competitionId));
  } catch {
    // Draft persistence is best-effort; a stale draft is safe to ignore.
  }
}
