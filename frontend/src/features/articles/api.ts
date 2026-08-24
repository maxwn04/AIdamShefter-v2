import { apiRequest } from "@/api/client";
import type { components } from "@/api/generated/schema";

export type SubmittedArticleResponse =
  components["schemas"]["SubmittedArticleResponse"];
export type ArticlePageResponse = components["schemas"]["ArticlePageResponse"];
export type ArticleSummary = components["schemas"]["ArticleSummary"];
export type GenerationKind = components["schemas"]["GenerationKind"];

export interface ArticleListParameters {
  competitionSeasonId?: string;
  kind?: GenerationKind;
  limit: number;
  offset: number;
}

export function listArticles(
  competitionId: string,
  parameters: ArticleListParameters,
  signal?: AbortSignal,
): Promise<ArticlePageResponse> {
  const query = new URLSearchParams({
    limit: String(parameters.limit),
    offset: String(parameters.offset),
  });
  if (parameters.competitionSeasonId) {
    query.set("competition_season_id", parameters.competitionSeasonId);
  }
  if (parameters.kind) query.set("kind", parameters.kind);

  return apiRequest(
    `/api/v1/generations/competitions/${competitionId}/articles?${query.toString()}`,
    { signal },
  );
}

export function getSubmittedArticle(
  competitionId: string,
  generationId: string,
  signal?: AbortSignal,
): Promise<SubmittedArticleResponse> {
  return apiRequest(
    `/api/v1/generations/competitions/${competitionId}/${generationId}/article`,
    { signal },
  );
}
