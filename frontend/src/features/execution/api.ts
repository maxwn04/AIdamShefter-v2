import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type AICall = components["schemas"]["AICall"];
export type AICallPageResponse = components["schemas"]["AICallPageResponse"];
export type AICallResponse = components["schemas"]["AICallResponse"];
export type AICallStatus = components["schemas"]["AICallStatus"];
export type AICallSummary = components["schemas"]["AICallSummary"];
export type GenerationMemoryRecall =
  components["schemas"]["GenerationMemoryRecall"];
export type GenerationMemoryRecallResponse =
  components["schemas"]["GenerationMemoryRecallResponse"];
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

const MAX_TOOL_CALL_PAGE_SIZE = 200;
const MEMORY_ACTIVITY_TOOL_NAMES = new Set([
  "search_memory",
  "save_memory_event",
  "upsert_storyline_memory_card",
  "save_storyline_trigger",
  "save_team_context",
  "save_league_note",
]);

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

export function getGenerationMemoryRecall(
  competitionId: string,
  generationId: string,
  signal?: AbortSignal,
): Promise<GenerationMemoryRecallResponse> {
  return apiRequest(
    `${generationPath(competitionId, generationId)}/memory-recall`,
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

export async function listGenerationToolCalls(
  competitionId: string,
  generationId: string,
  signal?: AbortSignal,
): Promise<ToolCallSummary[]> {
  const items: ToolCallSummary[] = [];
  let offset = 0;

  for (;;) {
    const response = await apiRequest<ToolCallPageResponse>(
      `${generationPath(competitionId, generationId)}/tool-calls?${pageQuery({ limit: MAX_TOOL_CALL_PAGE_SIZE, offset }).toString()}`,
      { signal },
    );
    items.push(...response.page.items);

    if (
      response.page.items.length === 0 ||
      items.length >= response.page.total
    ) {
      return items;
    }
    offset += response.page.items.length;
  }
}

export async function listGenerationMemoryToolCalls(
  competitionId: string,
  generationId: string,
  signal?: AbortSignal,
): Promise<ToolCall[]> {
  const summaries = await listGenerationToolCalls(
    competitionId,
    generationId,
    signal,
  );
  const memoryCalls = summaries.filter(
    (summary) =>
      summary.status === "succeeded" &&
      MEMORY_ACTIVITY_TOOL_NAMES.has(summary.tool_name),
  );
  const responses = await Promise.all(
    memoryCalls.map((summary) =>
      getToolCall(competitionId, generationId, summary.id, signal),
    ),
  );
  return responses.map((response) => response.tool_call);
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
