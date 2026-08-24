import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type ModelCatalogItem = components["schemas"]["ModelCatalogItem"];
export type ModelCatalogResponse =
  components["schemas"]["ModelCatalogResponse"];

export function getModelCatalog(
  signal?: AbortSignal,
): Promise<ModelCatalogResponse> {
  return apiRequest("/api/v1/models", { signal });
}
