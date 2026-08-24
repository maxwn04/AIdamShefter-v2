export const queryKeys = {
  health: {
    all: ["health"] as const,
    status: () => ["health", "status"] as const,
  },
  competitions: {
    all: ["competitions"] as const,
    list: (filters: Readonly<Record<string, unknown>> = {}) =>
      ["competitions", "list", filters] as const,
    detail: (competitionId: string) =>
      ["competitions", competitionId, "detail"] as const,
    seasons: (competitionId: string) =>
      ["competitions", competitionId, "seasons"] as const,
  },
} as const;
