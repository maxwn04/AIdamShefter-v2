import type { GenerationKind } from "@/features/articles/api";

export const ARTICLE_PAGE_SIZE = 25;

export function positiveArticlePage(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

export function articleKind(
  value: string | null,
): GenerationKind | undefined {
  return value === "live" || value === "backtest" ? value : undefined;
}

function querySuffix(parameters: URLSearchParams): string {
  const query = parameters.toString();
  return query ? `?${query}` : "";
}

export function articleReaderPath(
  competitionId: string,
  generationId: string,
  librarySearch: URLSearchParams,
): string {
  const context = new URLSearchParams();
  const season = librarySearch.get("season");
  const kind = articleKind(librarySearch.get("kind"));
  const page = positiveArticlePage(librarySearch.get("page"));

  if (season) context.set("season", season);
  if (kind) context.set("kind", kind);
  if (page > 1) context.set("libraryPage", String(page));

  return `/competitions/${competitionId}/articles/${generationId}${querySuffix(context)}`;
}

export function siblingArticlePath(
  competitionId: string,
  generationId: string,
  readerSearch: URLSearchParams,
): string {
  const context = new URLSearchParams();
  const season = readerSearch.get("season");
  const kind = articleKind(readerSearch.get("kind"));
  const page = positiveArticlePage(readerSearch.get("libraryPage"));

  if (season) context.set("season", season);
  if (kind) context.set("kind", kind);
  if (page > 1) context.set("libraryPage", String(page));

  return `/competitions/${competitionId}/articles/${generationId}${querySuffix(context)}`;
}

export function articleLibraryPath(
  competitionId: string,
  readerSearch: URLSearchParams,
): string {
  const context = new URLSearchParams();
  const season = readerSearch.get("season");
  const kind = articleKind(readerSearch.get("kind"));
  const page = positiveArticlePage(readerSearch.get("libraryPage"));

  if (season) context.set("season", season);
  if (kind) context.set("kind", kind);
  if (page > 1) context.set("page", String(page));

  return `/competitions/${competitionId}/articles${querySuffix(context)}`;
}
