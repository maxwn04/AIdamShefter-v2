import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type CompetitionSeason = components["schemas"]["CompetitionSeason"];
export type CompetitionSeasonOverview =
  components["schemas"]["CompetitionSeasonOverview"];
export type CompetitionSeasonDetailResponse =
  components["schemas"]["CompetitionSeasonDetailResponse"];
export type CompetitionSeasonPageResponse =
  components["schemas"]["CompetitionSeasonPageResponse"];
export type CompetitionSeasonResponse =
  components["schemas"]["CompetitionSeasonResponse"];

export interface SeasonListParameters {
  limit: number;
  offset: number;
}

export function listSeasons(
  competitionId: string,
  parameters: SeasonListParameters,
  signal?: AbortSignal,
): Promise<CompetitionSeasonPageResponse> {
  const query = new URLSearchParams({
    limit: String(parameters.limit),
    offset: String(parameters.offset),
  });
  return apiRequest(
    `/api/v1/competitions/${competitionId}/seasons?${query.toString()}`,
    { signal },
  );
}

export function getSeason(
  competitionId: string,
  seasonId: string,
  signal?: AbortSignal,
): Promise<CompetitionSeasonDetailResponse> {
  return apiRequest(
    `/api/v1/competitions/${competitionId}/seasons/${seasonId}`,
    { signal },
  );
}

export function createSeason(
  competitionId: string,
  values: { seasonYear: number; sleeperLeagueId: string },
): Promise<CompetitionSeasonResponse> {
  return apiRequest(`/api/v1/competitions/${competitionId}/seasons`, {
    method: "POST",
    json: {
      season_year: values.seasonYear,
      sleeper_league_id: values.sleeperLeagueId,
    },
  });
}
