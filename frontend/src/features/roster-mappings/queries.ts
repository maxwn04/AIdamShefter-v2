import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import {
  getRosterMappings,
  putRosterMappings,
  type PutRosterMappingsBody,
} from "@/features/roster-mappings/api";

export function useRosterMappings(
  competitionId: string | undefined,
  seasonId: string | undefined,
) {
  return useQuery({
    queryKey: queryKeys.competitions.rosterMappings(
      competitionId ?? "missing",
      seasonId ?? "missing",
    ),
    queryFn: ({ signal }) =>
      getRosterMappings(competitionId ?? "", seasonId ?? "", signal),
    enabled: competitionId !== undefined && seasonId !== undefined,
  });
}

export function usePutRosterMappings(competitionId: string, seasonId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PutRosterMappingsBody) =>
      putRosterMappings(competitionId, seasonId, body),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.rosterMappings(
            competitionId,
            seasonId,
          ),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.seasonDetail(
            competitionId,
            seasonId,
          ),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.seasons(competitionId),
        }),
      ]);
    },
  });
}
