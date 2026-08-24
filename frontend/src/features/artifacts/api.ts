import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type Artifact = components["schemas"]["Artifact"];
export type ArtifactSummary = components["schemas"]["ArtifactSummary"];
export type ArtifactPageResponse =
  components["schemas"]["ArtifactPageResponse"];
export type ArtifactVersion = components["schemas"]["ArtifactVersion"];
export type ArtifactVersionSummary =
  components["schemas"]["ArtifactVersionSummary"];
export type ArtifactVersionPageResponse =
  components["schemas"]["ArtifactVersionPageResponse"];
export type ArtifactVersionResponse =
  components["schemas"]["ArtifactVersionResponse"];

export interface PageParameters {
  limit: number;
  offset: number;
}

export function listArtifacts(
  competitionId: string,
  generationId: string,
  parameters: PageParameters,
  signal?: AbortSignal,
): Promise<ArtifactPageResponse> {
  const query = new URLSearchParams({
    limit: String(parameters.limit),
    offset: String(parameters.offset),
  });
  return apiRequest(
    `/api/v1/generations/competitions/${competitionId}/${generationId}/artifacts?${query.toString()}`,
    { signal },
  );
}

export function listArtifactVersions(
  competitionId: string,
  generationId: string,
  artifactId: string,
  parameters: PageParameters,
  signal?: AbortSignal,
): Promise<ArtifactVersionPageResponse> {
  const query = new URLSearchParams({
    limit: String(parameters.limit),
    offset: String(parameters.offset),
  });
  return apiRequest(
    `/api/v1/generations/competitions/${competitionId}/${generationId}/artifacts/${artifactId}/versions?${query.toString()}`,
    { signal },
  );
}

export function getArtifactVersion(
  competitionId: string,
  generationId: string,
  artifactId: string,
  versionId: string,
  signal?: AbortSignal,
): Promise<ArtifactVersionResponse> {
  return apiRequest(
    `/api/v1/generations/competitions/${competitionId}/${generationId}/artifacts/${artifactId}/versions/${versionId}`,
    { signal },
  );
}
