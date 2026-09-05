import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type SnapshotPreparationBody =
  components["schemas"]["SnapshotPreparationBody"];
export type SnapshotPreparationMode =
  components["schemas"]["SnapshotPreparationMode"];
export type SnapshotPreparationResponse =
  components["schemas"]["SnapshotPreparationResponse"];
export type SnapshotReadinessResponse =
  components["schemas"]["SnapshotReadinessResponse"];
export type SnapshotReadinessState = SnapshotReadinessResponse["state"];

export interface SnapshotReadinessParameters {
  throughWeek: number;
  mode: SnapshotPreparationMode;
}

const READINESS_TIMEOUT_MS = 30_000;
const PREPARATION_TIMEOUT_MS = 300_000;

function snapshotBase(competitionId: string, seasonId: string): string {
  return `/api/v1/data/competitions/${competitionId}/seasons/${seasonId}`;
}

function boundedSignal(
  timeoutMilliseconds: number,
  signal?: AbortSignal,
): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMilliseconds);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

export function snapshotReadinessPath(
  competitionId: string,
  seasonId: string,
  parameters: SnapshotReadinessParameters,
): string {
  const query = new URLSearchParams({
    through_week: String(parameters.throughWeek),
    mode: parameters.mode,
  });
  return `${snapshotBase(competitionId, seasonId)}/snapshot-readiness?${query.toString()}`;
}

export function getSnapshotReadiness(
  competitionId: string,
  seasonId: string,
  parameters: SnapshotReadinessParameters,
  signal?: AbortSignal,
): Promise<SnapshotReadinessResponse> {
  return apiRequest(
    snapshotReadinessPath(competitionId, seasonId, parameters),
    {
      signal: boundedSignal(READINESS_TIMEOUT_MS, signal),
    },
  );
}

export function prepareSnapshot(
  competitionId: string,
  seasonId: string,
  body: SnapshotPreparationBody,
): Promise<SnapshotPreparationResponse> {
  return apiRequest(
    `${snapshotBase(competitionId, seasonId)}/snapshot-preparations`,
    {
      method: "POST",
      json: body,
      signal: boundedSignal(PREPARATION_TIMEOUT_MS),
    },
  );
}
