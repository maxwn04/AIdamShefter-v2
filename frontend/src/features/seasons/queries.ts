import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import {
  createSeason,
  getSeason,
  listSeasons,
  type SeasonListParameters,
} from "@/features/seasons/api";

export function useSeasonList(
  competitionId: string | undefined,
  parameters: SeasonListParameters,
) {
  return useQuery({
    queryKey: queryKeys.competitions.seasons(competitionId ?? "missing"),
    queryFn: ({ signal }) =>
      listSeasons(competitionId ?? "", parameters, signal),
    enabled: competitionId !== undefined,
  });
}

export function useSeasonDetail(
  competitionId: string | undefined,
  seasonId: string | undefined,
) {
  return useQuery({
    queryKey: queryKeys.competitions.seasonDetail(
      competitionId ?? "missing",
      seasonId ?? "missing",
    ),
    queryFn: ({ signal }) =>
      getSeason(competitionId ?? "", seasonId ?? "", signal),
    enabled: competitionId !== undefined && seasonId !== undefined,
  });
}

export function useCreateSeason(competitionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (values: { seasonYear: number; sleeperLeagueId: string }) =>
      createSeason(competitionId, values),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.all,
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.seasons(competitionId),
        }),
      ]);
    },
  });
}
