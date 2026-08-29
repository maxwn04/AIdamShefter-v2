import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/api/errors";
import { queryKeys } from "@/api/query-keys";
import {
  getSnapshotReadiness,
  prepareSnapshot,
  type SnapshotPreparationBody,
  type SnapshotPreparationResponse,
  type SnapshotReadinessParameters,
} from "@/features/snapshot-readiness/api";

export function preparationAffectedSeasonIds(
  primarySeasonId: string,
  response: SnapshotPreparationResponse | undefined,
  error: Error | null,
): readonly string[] {
  const affected = new Set([primarySeasonId]);
  for (const receipt of response?.refresh_receipts ?? []) {
    affected.add(receipt.competition_season_id);
  }
  if (error instanceof ApiError && error.competitionSeasonId) {
    affected.add(error.competitionSeasonId);
  }
  return [...affected];
}

export function preparationInvalidationKeys(
  competitionId: string,
  primarySeasonId: string,
  response: SnapshotPreparationResponse | undefined,
  error: Error | null,
): readonly (readonly unknown[])[] {
  const affectedSeasonIds = preparationAffectedSeasonIds(
    primarySeasonId,
    response,
    error,
  );
  return [
    queryKeys.competitions.snapshotReadinessScope(
      competitionId,
      primarySeasonId,
    ),
    queryKeys.competitions.snapshots(competitionId, primarySeasonId),
    ...affectedSeasonIds.flatMap((seasonId) => [
      queryKeys.competitions.refreshes(competitionId, seasonId),
      queryKeys.competitions.seasonDetail(competitionId, seasonId),
      queryKeys.competitions.rosterMappings(competitionId, seasonId),
    ]),
  ];
}

export function useSnapshotReadiness(
  competitionId: string | undefined,
  seasonId: string | undefined,
  parameters: SnapshotReadinessParameters,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.competitions.snapshotReadiness(
      competitionId ?? "missing",
      seasonId ?? "missing",
      parameters,
    ),
    queryFn: ({ signal }) =>
      getSnapshotReadiness(
        competitionId ?? "",
        seasonId ?? "",
        parameters,
        signal,
      ),
    enabled: enabled && competitionId !== undefined && seasonId !== undefined,
    retry: 1,
  });
}

export function usePrepareSnapshot(
  competitionId: string,
  primarySeasonId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: queryKeys.competitions.snapshotPreparation(
      competitionId,
      primarySeasonId,
    ),
    mutationFn: (body: SnapshotPreparationBody) =>
      prepareSnapshot(competitionId, primarySeasonId, body),
    onSettled: async (response, error) => {
      const invalidationKeys = preparationInvalidationKeys(
        competitionId,
        primarySeasonId,
        response,
        error,
      );
      await Promise.all(
        invalidationKeys.map((queryKey) =>
          queryClient.invalidateQueries({ queryKey }),
        ),
      );
    },
  });
}
