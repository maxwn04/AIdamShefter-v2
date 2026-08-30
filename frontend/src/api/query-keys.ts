export const queryKeys = {
  health: {
    all: ["health"] as const,
    status: () => ["health", "status"] as const,
  },
  models: {
    all: ["models"] as const,
    catalog: () => ["models", "catalog"] as const,
  },
  competitions: {
    all: ["competitions"] as const,
    lists: () => ["competitions", "list"] as const,
    list: (filters: Readonly<object> = {}) =>
      ["competitions", "list", filters] as const,
    detail: (competitionId: string) =>
      ["competitions", competitionId, "detail"] as const,
    seasons: (competitionId: string) =>
      ["competitions", competitionId, "seasons"] as const,
    seasonDetail: (competitionId: string, seasonId: string) =>
      ["competitions", competitionId, "seasons", seasonId] as const,
    rosterMappings: (competitionId: string, seasonId: string) =>
      [
        "competitions",
        competitionId,
        "seasons",
        seasonId,
        "roster-mappings",
      ] as const,
    refreshes: (competitionId: string, seasonId: string) =>
      [
        "competitions",
        competitionId,
        "seasons",
        seasonId,
        "refreshes",
      ] as const,
    refreshList: (
      competitionId: string,
      seasonId: string,
      page: Readonly<object>,
    ) =>
      [
        "competitions",
        competitionId,
        "seasons",
        seasonId,
        "refreshes",
        "list",
        page,
      ] as const,
    refreshDetail: (
      competitionId: string,
      seasonId: string,
      refreshId: string,
    ) =>
      [
        "competitions",
        competitionId,
        "seasons",
        seasonId,
        "refreshes",
        refreshId,
      ] as const,
    snapshots: (competitionId: string, seasonId: string) =>
      [
        "competitions",
        competitionId,
        "seasons",
        seasonId,
        "snapshots",
      ] as const,
    generations: (competitionId: string) =>
      ["competitions", competitionId, "generations"] as const,
    generationList: (competitionId: string, parameters: Readonly<object>) =>
      [
        "competitions",
        competitionId,
        "generations",
        "list",
        parameters,
      ] as const,
    generationSubmission: (competitionId: string) =>
      ["competitions", competitionId, "generations", "submit"] as const,
    generationRerun: (competitionId: string, generationId: string) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "rerun",
      ] as const,
    generationDetail: (competitionId: string, generationId: string) =>
      ["competitions", competitionId, "generations", generationId] as const,
    articleLists: (competitionId: string) =>
      ["competitions", competitionId, "articles", "list"] as const,
    articleList: (competitionId: string, parameters: Readonly<object>) =>
      ["competitions", competitionId, "articles", "list", parameters] as const,
    submittedArticle: (competitionId: string, generationId: string) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "article",
      ] as const,
    artifactLists: (competitionId: string, generationId: string) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "artifacts",
        "list",
      ] as const,
    artifactList: (
      competitionId: string,
      generationId: string,
      parameters: Readonly<object>,
    ) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "artifacts",
        "list",
        parameters,
      ] as const,
    artifactVersionLists: (
      competitionId: string,
      generationId: string,
      artifactId: string,
    ) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "artifacts",
        artifactId,
        "versions",
        "list",
      ] as const,
    artifactVersionList: (
      competitionId: string,
      generationId: string,
      artifactId: string,
      parameters: Readonly<object>,
    ) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "artifacts",
        artifactId,
        "versions",
        "list",
        parameters,
      ] as const,
    artifactVersionDetail: (
      competitionId: string,
      generationId: string,
      artifactId: string,
      versionId: string,
    ) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "artifacts",
        artifactId,
        "versions",
        versionId,
      ] as const,
    generationUsage: (competitionId: string, generationId: string) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "usage",
      ] as const,
    generationMemoryRecall: (competitionId: string, generationId: string) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "memory-recall",
      ] as const,
    aiCallLists: (competitionId: string, generationId: string) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "ai-calls",
        "list",
      ] as const,
    aiCallList: (
      competitionId: string,
      generationId: string,
      parameters: Readonly<object>,
    ) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "ai-calls",
        "list",
        parameters,
      ] as const,
    aiCallDetail: (
      competitionId: string,
      generationId: string,
      aiCallId: string,
    ) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "ai-calls",
        aiCallId,
      ] as const,
    toolCallLists: (
      competitionId: string,
      generationId: string,
      aiCallId: string,
    ) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "ai-calls",
        aiCallId,
        "tool-calls",
        "list",
      ] as const,
    generationToolCallList: (competitionId: string, generationId: string) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "tool-calls",
        "list",
      ] as const,
    toolCallList: (
      competitionId: string,
      generationId: string,
      aiCallId: string,
      parameters: Readonly<object>,
    ) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "ai-calls",
        aiCallId,
        "tool-calls",
        "list",
        parameters,
      ] as const,
    toolCallDetail: (
      competitionId: string,
      generationId: string,
      aiCallId: string,
      toolCallId: string,
    ) =>
      [
        "competitions",
        competitionId,
        "generations",
        generationId,
        "ai-calls",
        aiCallId,
        "tool-calls",
        toolCallId,
      ] as const,
  },
} as const;
