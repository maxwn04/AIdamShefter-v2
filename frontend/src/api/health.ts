import type { components } from "@/api/generated/schema";
import { apiRequest } from "@/api/client";
import { ApiError } from "@/api/errors";

type HealthResponse = components["schemas"]["HealthResponse"];

export interface ApiHealth {
  state: "ready" | "online";
  summary: string;
}

export async function getApiHealth(signal?: AbortSignal): Promise<ApiHealth> {
  await apiRequest<HealthResponse>("/health/live", { signal });

  try {
    await apiRequest<HealthResponse>("/health/ready", { signal });
    return { state: "ready", summary: "API ready" };
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      return { state: "online", summary: "API starting" };
    }
    throw error;
  }
}
