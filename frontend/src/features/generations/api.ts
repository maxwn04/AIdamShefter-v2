import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type Generation = components["schemas"]["Generation"];
export type GenerationBiasSettings =
  components["schemas"]["GenerationBiasSettings"];
export type GenerationKind = components["schemas"]["GenerationKind"];
export type GenerationModelSettings =
  components["schemas"]["GenerationModelSettings"];
export type GenerationReportSettings =
  components["schemas"]["GenerationReportSettings"];
export type GenerationResponse = components["schemas"]["GenerationResponse"];
export type GenerationRetrySettings =
  components["schemas"]["GenerationRetrySettings"];
export type GenerationRunnerSettings =
  components["schemas"]["GenerationRunnerSettings"];
export type GenerationSettings = components["schemas"]["GenerationSettings"];
export type GenerationToneSettings =
  components["schemas"]["GenerationToneSettings"];
export type SubmitGenerationBody =
  components["schemas"]["SubmitGenerationBody"];

export interface SubmitGenerationInput {
  competitionId: string;
  body: SubmitGenerationBody;
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
