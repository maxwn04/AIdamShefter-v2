import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type Competition = components["schemas"]["Competition"];
export type CompetitionOverview = components["schemas"]["CompetitionOverview"];
export type CompetitionOverviewResponse =
  components["schemas"]["CompetitionOverviewResponse"];
export type CompetitionPageResponse =
  components["schemas"]["CompetitionPageResponse"];
export type CompetitionResponse = components["schemas"]["CompetitionResponse"];

export interface CompetitionListParameters {
  includeArchived?: boolean;
  limit: number;
  offset: number;
}

export function listCompetitions(
  parameters: CompetitionListParameters,
  signal?: AbortSignal,
): Promise<CompetitionPageResponse> {
  const query = new URLSearchParams({
    include_archived: String(parameters.includeArchived ?? false),
    limit: String(parameters.limit),
    offset: String(parameters.offset),
  });
  return apiRequest(`/api/v1/competitions?${query.toString()}`, { signal });
}

export function getCompetition(
  competitionId: string,
  signal?: AbortSignal,
): Promise<CompetitionOverviewResponse> {
  return apiRequest(`/api/v1/competitions/${competitionId}`, { signal });
}

export function createCompetition(
  displayName: string,
): Promise<CompetitionResponse> {
  return apiRequest("/api/v1/competitions", {
    method: "POST",
    json: { display_name: displayName },
  });
}

export function archiveCompetition(
  competitionId: string,
): Promise<CompetitionResponse> {
  return apiRequest(`/api/v1/competitions/${competitionId}`, {
    method: "PATCH",
    json: { archived: true },
  });
}
