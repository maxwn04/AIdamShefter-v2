import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type AICall = components["schemas"]["AICall"];
export type AICallPageResponse = components["schemas"]["AICallPageResponse"];
export type AICallResponse = components["schemas"]["AICallResponse"];
export type AICallStatus = components["schemas"]["AICallStatus"];
export type AICallSummary = components["schemas"]["AICallSummary"];
export type TokenUsage = components["schemas"]["TokenUsage"];
export type ToolCall = components["schemas"]["ToolCall"];
export type ToolCallPageResponse =
  components["schemas"]["ToolCallPageResponse"];
export type ToolCallResponse = components["schemas"]["ToolCallResponse"];
export type ToolCallStatus = components["schemas"]["ToolCallStatus"];
export type ToolCallSummary = components["schemas"]["ToolCallSummary"];

export interface ExecutionPageParameters {
  limit: number;
  offset: number;
}

function generationPath(competitionId: string, generationId: string): string {
  return `/api/v1/generations/competitions/${competitionId}/${generationId}`;
}

function pageQuery(parameters: ExecutionPageParameters): URLSearchParams {
  return new URLSearchParams({
    limit: String(parameters.limit),
    offset: String(parameters.offset),
  });
}

export function listAICalls(
  competitionId: string,
  generationId: string,
  parameters: ExecutionPageParameters,
  signal?: AbortSignal,
): Promise<AICallPageResponse> {
  return apiRequest(
    `${generationPath(competitionId, generationId)}/ai-calls?${pageQuery(parameters).toString()}`,
    { signal },
  );
}

export function getAICall(
  competitionId: string,
  generationId: string,
  aiCallId: string,
  signal?: AbortSignal,
): Promise<AICallResponse> {
  return apiRequest(
    `${generationPath(competitionId, generationId)}/ai-calls/${aiCallId}`,
    { signal },
  );
}

export function listToolCalls(
  competitionId: string,
  generationId: string,
  aiCallId: string,
  parameters: ExecutionPageParameters,
  signal?: AbortSignal,
): Promise<ToolCallPageResponse> {
  const query = pageQuery(parameters);
  query.set("ai_call_id", aiCallId);
  return apiRequest(
    `${generationPath(competitionId, generationId)}/tool-calls?${query.toString()}`,
    { signal },
  );
}

export function getToolCall(
  competitionId: string,
  generationId: string,
  toolCallId: string,
  signal?: AbortSignal,
): Promise<ToolCallResponse> {
  return apiRequest(
    `${generationPath(competitionId, generationId)}/tool-calls/${toolCallId}`,
    { signal },
  );
}
