import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import {
  getAICall,
  getToolCall,
  listGenerationToolCalls,
  listAICalls,
  listToolCalls,
  type ExecutionPageParameters,
} from "@/features/execution/api";

const ACTIVE_SUMMARY_POLL_MS = 2_000;

function browserCanPoll(): boolean {
  return (
    typeof document === "undefined" ||
    (document.visibilityState === "visible" && navigator.onLine)
  );
}

export function useAICallList(
  competitionId: string,
  generationId: string,
  parameters: ExecutionPageParameters,
  enabled: boolean,
  generationActive: boolean,
) {
  return useQuery({
    queryKey: [
      ...queryKeys.competitions.aiCallList(
        competitionId,
        generationId,
        parameters,
      ),
      generationActive,
    ] as const,
    queryFn: ({ signal }) =>
      listAICalls(competitionId, generationId, parameters, signal),
    enabled: enabled && competitionId.length > 0 && generationId.length > 0,
    placeholderData: keepPreviousData,
    refetchInterval:
      enabled && generationActive && browserCanPoll()
        ? ACTIVE_SUMMARY_POLL_MS
        : false,
    refetchIntervalInBackground: false,
  });
}

export function useAICallDetail(
  competitionId: string,
  generationId: string,
  aiCallId: string,
  enabled: boolean,
  poll: boolean,
) {
  return useQuery({
    queryKey: queryKeys.competitions.aiCallDetail(
      competitionId,
      generationId,
      aiCallId,
    ),
    queryFn: ({ signal }) =>
      getAICall(competitionId, generationId, aiCallId, signal),
    enabled:
      enabled &&
      competitionId.length > 0 &&
      generationId.length > 0 &&
      aiCallId.length > 0,
    refetchInterval:
      enabled && poll && browserCanPoll() ? ACTIVE_SUMMARY_POLL_MS : false,
    refetchIntervalInBackground: false,
  });
}

export function useGenerationToolCallList(
  competitionId: string,
  generationId: string,
  enabled: boolean,
  generationActive: boolean,
) {
  return useQuery({
    queryKey: queryKeys.competitions.generationToolCallList(
      competitionId,
      generationId,
    ),
    queryFn: ({ signal }) =>
      listGenerationToolCalls(competitionId, generationId, signal),
    enabled: enabled && competitionId.length > 0 && generationId.length > 0,
    refetchInterval:
      enabled && generationActive && browserCanPoll()
        ? ACTIVE_SUMMARY_POLL_MS
        : false,
    refetchIntervalInBackground: false,
  });
}

export function useToolCallList(
  competitionId: string,
  generationId: string,
  aiCallId: string,
  parameters: ExecutionPageParameters,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.competitions.toolCallList(
      competitionId,
      generationId,
      aiCallId,
      parameters,
    ),
    queryFn: ({ signal }) =>
      listToolCalls(competitionId, generationId, aiCallId, parameters, signal),
    enabled:
      enabled &&
      competitionId.length > 0 &&
      generationId.length > 0 &&
      aiCallId.length > 0,
    placeholderData: keepPreviousData,
  });
}

export function useToolCallDetail(
  competitionId: string,
  generationId: string,
  aiCallId: string,
  toolCallId: string,
  enabled: boolean,
  poll: boolean,
) {
  return useQuery({
    queryKey: queryKeys.competitions.toolCallDetail(
      competitionId,
      generationId,
      aiCallId,
      toolCallId,
    ),
    queryFn: ({ signal }) =>
      getToolCall(competitionId, generationId, toolCallId, signal),
    enabled:
      enabled &&
      competitionId.length > 0 &&
      generationId.length > 0 &&
      aiCallId.length > 0 &&
      toolCallId.length > 0,
    refetchInterval:
      enabled && poll && browserCanPoll() ? ACTIVE_SUMMARY_POLL_MS : false,
    refetchIntervalInBackground: false,
  });
}
