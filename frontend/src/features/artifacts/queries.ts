import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import {
  getArtifactVersion,
  listArtifacts,
  listArtifactVersions,
  type PageParameters,
} from "@/features/artifacts/api";

export function useArtifactList(
  competitionId: string,
  generationId: string,
  parameters: PageParameters,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.competitions.artifactList(
      competitionId,
      generationId,
      parameters,
    ),
    queryFn: ({ signal }) =>
      listArtifacts(competitionId, generationId, parameters, signal),
    enabled: enabled && competitionId.length > 0 && generationId.length > 0,
  });
}

export function useArtifactVersionList(
  competitionId: string,
  generationId: string,
  artifactId: string | undefined,
  parameters: PageParameters,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.competitions.artifactVersionList(
      competitionId,
      generationId,
      artifactId ?? "missing",
      parameters,
    ),
    queryFn: ({ signal }) =>
      listArtifactVersions(
        competitionId,
        generationId,
        artifactId ?? "",
        parameters,
        signal,
      ),
    enabled:
      enabled &&
      competitionId.length > 0 &&
      generationId.length > 0 &&
      artifactId !== undefined,
  });
}

export function useArtifactVersion(
  competitionId: string,
  generationId: string,
  artifactId: string | undefined,
  versionId: string | undefined,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.competitions.artifactVersionDetail(
      competitionId,
      generationId,
      artifactId ?? "missing",
      versionId ?? "missing",
    ),
    queryFn: ({ signal }) =>
      getArtifactVersion(
        competitionId,
        generationId,
        artifactId ?? "",
        versionId ?? "",
        signal,
      ),
    enabled:
      enabled &&
      competitionId.length > 0 &&
      generationId.length > 0 &&
      artifactId !== undefined &&
      versionId !== undefined,
  });
}
