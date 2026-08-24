import { useMutation, useQueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import {
  submitGeneration,
  type GenerationResponse,
  type SubmitGenerationBody,
} from "@/features/generations/api";

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
