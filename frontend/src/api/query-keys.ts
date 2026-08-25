export const queryKeys = {
  health: {
    all: ["health"] as const,
    status: () => ["health", "status"] as const,
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
  },
} as const;
