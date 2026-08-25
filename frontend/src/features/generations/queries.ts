import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import {
  getGeneration,
  getGenerationHistory,
  rerunGeneration,
  submitGeneration,
  type GenerationDetailResponse,
  type GenerationResponse,
  type GenerationStatus,
  type SubmitGenerationBody,
} from "@/features/generations/api";

const GENERATION_POLL_INTERVAL_MS = 2_000;

function isActiveGeneration(status: GenerationStatus | undefined): boolean {
  return status === "pending" || status === "running";
}

function canPollInBrowser(): boolean {
  return (
    typeof document === "undefined" ||
    (document.visibilityState === "visible" && navigator.onLine)
  );
}

export function useSubmitGeneration(competitionId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: queryKeys.competitions.generationSubmission(competitionId),
    mutationFn: (body: SubmitGenerationBody) =>
      submitGeneration({ competitionId, body }),
    onSuccess: async (response: GenerationResponse) => {
      queryClient.setQueryData(
        queryKeys.competitions.generationDetail(
          competitionId,
          response.generation.id,
        ),
        response,
      );
      await queryClient.invalidateQueries({
        queryKey: queryKeys.competitions.generations(competitionId),
      });
    },
  });
}

export function useGenerationDetail(
  competitionId: string,
  generationId: string | undefined,
) {
  return useQuery({
    queryKey: queryKeys.competitions.generationDetail(
      competitionId,
      generationId ?? "missing",
    ),
    queryFn: ({ signal }) =>
      getGeneration(competitionId, generationId ?? "", signal),
    enabled: generationId !== undefined,
    refetchInterval: (query) =>
      isActiveGeneration(query.state.data?.generation.status) &&
      canPollInBrowser()
        ? GENERATION_POLL_INTERVAL_MS
        : false,
    refetchIntervalInBackground: false,
    refetchOnReconnect: (query) =>
      isActiveGeneration(query.state.data?.generation.status)
        ? "always"
        : false,
    refetchOnWindowFocus: (query) =>
      isActiveGeneration(query.state.data?.generation.status)
        ? "always"
        : false,
  });
}

export function useGenerationHistory(
  competitionId: string,
  seasonId: string | undefined,
  limit = 5,
) {
  const parameters = {
    competitionSeasonId: seasonId ?? "",
    limit,
    offset: 0,
  } as const;
  return useQuery({
    queryKey: queryKeys.competitions.generationList(competitionId, parameters),
    queryFn: ({ signal }) =>
      getGenerationHistory(competitionId, parameters, signal),
    enabled:
      competitionId.length > 0 && seasonId !== undefined && seasonId.length > 0,
  });
}

export function useRerunGeneration(
  competitionId: string,
  generationId: string,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationKey: queryKeys.competitions.generationRerun(
      competitionId,
      generationId,
    ),
    mutationFn: () => rerunGeneration(competitionId, generationId),
    onSuccess: async (response: GenerationResponse) => {
      queryClient.setQueryData<GenerationDetailResponse>(
        queryKeys.competitions.generationDetail(
          competitionId,
          response.generation.id,
        ),
        response,
      );
      await queryClient.invalidateQueries({
        queryKey: queryKeys.competitions.generations(competitionId),
      });
    },
  });
}
