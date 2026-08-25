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
  },
} as const;
