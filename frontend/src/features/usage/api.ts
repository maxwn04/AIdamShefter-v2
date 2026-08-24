import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type GenerationUsage = components["schemas"]["GenerationUsage"];
export type GenerationUsageResponse =
  components["schemas"]["GenerationUsageResponse"];
export type ModelUsageBreakdown = components["schemas"]["ModelUsageBreakdown"];
export type TokenTotals = components["schemas"]["TokenTotals"];

export function getGenerationUsage(
  competitionId: string,
  generationId: string,
  signal?: AbortSignal,
): Promise<GenerationUsageResponse> {
  return apiRequest(
    `/api/v1/generations/competitions/${competitionId}/${generationId}/usage`,
    { signal },
  );
}
