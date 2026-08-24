import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type FranchiseIdentity = components["schemas"]["FranchiseIdentity"];
export type ObservedRosterMapping =
  components["schemas"]["ObservedRosterMapping"];
export type PutRosterMappingsBody =
  components["schemas"]["PutRosterMappingsBody"];
export type RosterMappingMutationResponse =
  components["schemas"]["RosterMappingMutationResponse"];
export type RosterMappingResponse =
  components["schemas"]["RosterMappingResponse"];
export type RosterMappingView = components["schemas"]["RosterMappingView"];

function mappingPath(competitionId: string, seasonId: string): string {
  return `/api/v1/competitions/${competitionId}/seasons/${seasonId}/roster-mappings`;
}

export function getRosterMappings(
  competitionId: string,
  seasonId: string,
  signal?: AbortSignal,
): Promise<RosterMappingResponse> {
  return apiRequest(mappingPath(competitionId, seasonId), { signal });
}

export function putRosterMappings(
  competitionId: string,
  seasonId: string,
  body: PutRosterMappingsBody,
): Promise<RosterMappingMutationResponse> {
  return apiRequest(mappingPath(competitionId, seasonId), {
    method: "PUT",
    json: body,
  });
}
