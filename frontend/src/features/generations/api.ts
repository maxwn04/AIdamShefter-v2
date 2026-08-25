import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type Generation = components["schemas"]["Generation"];
export type GenerationBiasSettings =
  components["schemas"]["GenerationBiasSettings"];
export type GenerationDetail = components["schemas"]["GenerationDetail"];
export type GenerationDetailResponse =
  components["schemas"]["GenerationDetailResponse"];
export type GenerationKind = components["schemas"]["GenerationKind"];
export type GenerationModelSettings =
  components["schemas"]["GenerationModelSettings"];
export type GenerationPageResponse =
  components["schemas"]["GenerationPageResponse"];
export type GenerationReportSettings =
  components["schemas"]["GenerationReportSettings"];
export type GenerationResponse = components["schemas"]["GenerationResponse"];
export type GenerationRetrySettings =
  components["schemas"]["GenerationRetrySettings"];
export type GenerationRunnerSettings =
  components["schemas"]["GenerationRunnerSettings"];
export type GenerationSettings = components["schemas"]["GenerationSettings"];
export type GenerationStatus = components["schemas"]["GenerationStatus"];
export type GenerationSummary = components["schemas"]["GenerationSummary"];
export type GenerationToneSettings =
  components["schemas"]["GenerationToneSettings"];
export type SubmitGenerationBody =
  components["schemas"]["SubmitGenerationBody"];

export interface SubmitGenerationInput {
  competitionId: string;
  body: SubmitGenerationBody;
}

export interface GenerationHistoryParameters {
  competitionSeasonId: string;
  limit: number;
  offset: number;
}

export function submitGeneration({
  competitionId,
  body,
}: SubmitGenerationInput): Promise<GenerationResponse> {
  return apiRequest(`/api/v1/generations/competitions/${competitionId}`, {
    method: "POST",
    json: body,
  });
}

export function getGeneration(
  competitionId: string,
  generationId: string,
  signal?: AbortSignal,
): Promise<GenerationDetailResponse> {
  return apiRequest(
    `/api/v1/generations/competitions/${competitionId}/${generationId}`,
    { signal },
  );
}

export function getGenerationHistory(
  competitionId: string,
  parameters: GenerationHistoryParameters,
  signal?: AbortSignal,
): Promise<GenerationPageResponse> {
  const query = new URLSearchParams({
    competition_season_id: parameters.competitionSeasonId,
    limit: String(parameters.limit),
    offset: String(parameters.offset),
  });
  return apiRequest(
    `/api/v1/generations/competitions/${competitionId}?${query.toString()}`,
    { signal },
  );
}

export function rerunGeneration(
  competitionId: string,
  generationId: string,
): Promise<GenerationResponse> {
  return apiRequest(
    `/api/v1/generations/competitions/${competitionId}/${generationId}/reruns`,
    { method: "POST" },
  );
}
