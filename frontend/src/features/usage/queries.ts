import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import { getGenerationUsage } from "@/features/usage/api";

export function useGenerationUsage(
  competitionId: string,
  generationId: string,
  enabled: boolean,
  provisional: boolean,
) {
  return useQuery({
    queryKey: [
      ...queryKeys.competitions.generationUsage(competitionId, generationId),
      provisional,
    ] as const,
    queryFn: ({ signal }) =>
      getGenerationUsage(competitionId, generationId, signal),
    enabled: enabled && competitionId.length > 0 && generationId.length > 0,
    refetchInterval:
      enabled &&
      provisional &&
      (typeof document === "undefined" ||
        (document.visibilityState === "visible" && navigator.onLine))
        ? 5_000
        : false,
    refetchIntervalInBackground: false,
  });
}
