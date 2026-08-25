import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import {
  getRefresh,
  listRefreshes,
  runManualRefresh,
  type RefreshListParameters,
} from "@/features/refreshes/api";

export function useRefreshList(
  competitionId: string,
  seasonId: string,
  parameters: RefreshListParameters,
) {
  return useQuery({
    queryKey: queryKeys.competitions.refreshList(
      competitionId,
      seasonId,
      parameters,
    ),
    queryFn: ({ signal }) =>
      listRefreshes(competitionId, seasonId, parameters, signal),
    placeholderData: keepPreviousData,
  });
}

export function useRefreshDetail(
  competitionId: string,
  seasonId: string,
  refreshId: string | undefined,
) {
  return useQuery({
    queryKey: queryKeys.competitions.refreshDetail(
      competitionId,
      seasonId,
      refreshId ?? "missing",
    ),
    queryFn: ({ signal }) =>
      getRefresh(competitionId, seasonId, refreshId ?? "", signal),
    enabled: refreshId !== undefined,
  });
}

export function useManualRefresh(competitionId: string, seasonId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (throughWeek?: number) =>
      runManualRefresh(competitionId, seasonId, throughWeek),
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.all,
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.seasons(competitionId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.seasonDetail(
            competitionId,
            seasonId,
          ),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.refreshes(competitionId, seasonId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.snapshots(competitionId, seasonId),
        }),
        queryClient.invalidateQueries({
          queryKey: queryKeys.competitions.rosterMappings(
            competitionId,
            seasonId,
          ),
        }),
      ]);
    },
  });
}
