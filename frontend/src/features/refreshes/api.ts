import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type ManualRefreshResponse =
  components["schemas"]["ManualRefreshResponse"];
export type RefreshRun = components["schemas"]["RefreshRun"];
export type RefreshRunPageResponse =
  components["schemas"]["RefreshRunPageResponse"];
export type RefreshRunResponse = components["schemas"]["RefreshRunResponse"];

export interface RefreshListParameters {
  limit: number;
  offset: number;
}

function refreshBase(competitionId: string, seasonId: string): string {
  return `/api/v1/data/competitions/${competitionId}/seasons/${seasonId}/refreshes`;
}

export function listRefreshes(
  competitionId: string,
  seasonId: string,
  parameters: RefreshListParameters,
  signal?: AbortSignal,
): Promise<RefreshRunPageResponse> {
  const query = new URLSearchParams({
    limit: String(parameters.limit),
    offset: String(parameters.offset),
  });
  return apiRequest(
    `${refreshBase(competitionId, seasonId)}?${query.toString()}`,
    {
      signal,
    },
  );
}

export function getRefresh(
  competitionId: string,
  seasonId: string,
  refreshId: string,
  signal?: AbortSignal,
): Promise<RefreshRunResponse> {
  return apiRequest(`${refreshBase(competitionId, seasonId)}/${refreshId}`, {
    signal,
  });
}

export function runManualRefresh(
  competitionId: string,
  seasonId: string,
  throughWeek?: number,
): Promise<ManualRefreshResponse> {
  return apiRequest(refreshBase(competitionId, seasonId), {
    method: "POST",
    json: throughWeek === undefined ? {} : { through_week: throughWeek },
    signal: AbortSignal.timeout(300_000),
  });
}
