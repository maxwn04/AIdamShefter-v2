import { ApiError, normalizeApiError } from "@/api/errors";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  json?: unknown;
}

function requestUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${configuredBaseUrl ?? ""}${normalizedPath}`;
}

async function parsePayload(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return undefined;

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("json")) return text;

  try {
    return JSON.parse(text) as unknown;
  } catch {
    if (response.ok) {
      throw new ApiError({
        status: response.status,
        code: "invalid_json_response",
        summary: "The API returned an invalid JSON response.",
      });
    }
    return text;
  }
}

export async function apiRequest<TResponse>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<TResponse> {
  const { json, ...requestOptions } = options;
  const headers = new Headers(options.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  if (!headers.has("X-Correlation-ID")) {
    headers.set("X-Correlation-ID", crypto.randomUUID());
  }
  if (json !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(requestUrl(path), {
      ...requestOptions,
      body: json === undefined ? undefined : JSON.stringify(json),
      headers,
    });
  } catch (error) {
    if (
      error instanceof DOMException &&
      (error.name === "AbortError" || error.name === "TimeoutError")
    )
      throw error;
    throw normalizeApiError(
      0,
      undefined,
      headers.get("X-Correlation-ID") ?? undefined,
    );
  }

  const payload = await parsePayload(response);
  if (!response.ok) {
    throw normalizeApiError(
      response.status,
      payload,
      response.headers.get("X-Correlation-ID") ??
        headers.get("X-Correlation-ID") ??
        undefined,
    );
  }

  return payload as TResponse;
}
