import type {
  SnapshotPreparationMode,
  SnapshotReadinessResponse,
} from "@/features/snapshot-readiness/api";

export function preparationModeForGeneration(
  generationMode: "live" | "backtest",
): SnapshotPreparationMode {
  return generationMode === "live" ? "live" : "readiness_only";
}

export function readinessAllowsGeneration(
  readiness: SnapshotReadinessResponse | undefined,
): boolean {
  return (
    readiness?.state.kind === "ready" ||
    readiness?.state.kind === "refresh_required"
  );
}
