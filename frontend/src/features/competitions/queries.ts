import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import {
  archiveCompetition,
  createCompetition,
  getCompetition,
  listCompetitions,
  type CompetitionListParameters,
} from "@/features/competitions/api";

export function useCompetitionList(parameters: CompetitionListParameters) {
  return useQuery({
    queryKey: queryKeys.competitions.list(parameters),
    queryFn: ({ signal }) => listCompetitions(parameters, signal),
    placeholderData: keepPreviousData,
  });
}

export function useCompetitionDetail(competitionId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.competitions.detail(competitionId ?? "missing"),
    queryFn: ({ signal }) => getCompetition(competitionId ?? "", signal),
    enabled: competitionId !== undefined,
  });
}

export function useCreateCompetition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCompetition,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.competitions.all,
      });
    },
  });
}

export function useArchiveCompetition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: archiveCompetition,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.competitions.all,
      });
    },
  });
}
