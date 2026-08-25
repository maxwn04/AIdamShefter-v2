import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import {
  getSubmittedArticle,
  listArticles,
  type ArticleListParameters,
} from "@/features/articles/api";

export function useArticleList(
  competitionId: string | undefined,
  parameters: ArticleListParameters,
) {
  return useQuery({
    queryKey: queryKeys.competitions.articleList(
      competitionId ?? "missing",
      parameters,
    ),
    queryFn: ({ signal }) =>
      listArticles(competitionId ?? "", parameters, signal),
    enabled: competitionId !== undefined,
  });
}

export function useSubmittedArticle(
  competitionId: string,
  generationId: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.competitions.submittedArticle(
      competitionId,
      generationId,
    ),
    queryFn: ({ signal }) =>
      getSubmittedArticle(competitionId, generationId, signal),
    enabled: enabled && competitionId.length > 0 && generationId.length > 0,
  });
}
