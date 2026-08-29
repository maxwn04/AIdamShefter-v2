import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { ApiError, normalizeApiError } from "@/api/errors";
import {
  snapshotReadinessPath,
  type SnapshotPreparationResponse,
  type SnapshotReadinessResponse,
} from "@/features/snapshot-readiness/api";
import {
  preparationModeForGeneration,
  readinessAllowsGeneration,
} from "@/features/snapshot-readiness/policy";
import {
  preparationAffectedSeasonIds,
  preparationInvalidationKeys,
} from "@/features/snapshot-readiness/queries";
import { SnapshotReadinessPanel } from "@/features/snapshot-readiness/readiness-panel";

const COMPETITION_ID = "20000000-0000-0000-0000-000000000001";
const PRIMARY_ID = "10000000-0000-0000-0000-000000000002";
const HISTORY_ID = "10000000-0000-0000-0000-000000000001";
const historicalSeason = {
  competition_season_id: HISTORY_ID,
  sleeper_league_id: "league-2025",
  season_year: 2025,
  sequence_number: 1,
  role: "history",
  through_week: 18,
} as const;
const primarySeason = {
  competition_season_id: PRIMARY_ID,
  sleeper_league_id: "league-2026",
  season_year: 2026,
  sequence_number: 2,
  role: "primary",
  through_week: 8,
} as const;

const ready: SnapshotReadinessResponse = {
  checked_at: "2026-08-29T22:00:00Z",
  mode: "readiness_only",
  through_week: 8,
  state: {
    kind: "ready",
    input_revision: "a".repeat(64),
    included_seasons: [historicalSeason, primarySeason],
  },
};

function renderPanel(
  readiness: SnapshotReadinessResponse | undefined,
  overrides: Partial<React.ComponentProps<typeof SnapshotReadinessPanel>> = {},
): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <SnapshotReadinessPanel
        competitionId={COMPETITION_ID}
        readiness={readiness}
        readinessPending={false}
        readinessError={null}
        preparation={undefined}
        preparationPending={false}
        preparationError={null}
        onRetry={() => undefined}
        onPrepare={() => undefined}
        {...overrides}
      />
    </MemoryRouter>,
  );
}

describe("snapshot readiness policy", () => {
  it("maps generation modes and gates only actionable readiness states", () => {
    expect(preparationModeForGeneration("live")).toBe("live");
    expect(preparationModeForGeneration("backtest")).toBe("readiness_only");
    expect(readinessAllowsGeneration(ready)).toBe(true);
    expect(
      readinessAllowsGeneration({
        ...ready,
        state: {
          kind: "refresh_required",
          reason: "missing",
          missing_scopes: ["League:history"],
          season: historicalSeason,
        },
      }),
    ).toBe(true);
    expect(
      readinessAllowsGeneration({
        ...ready,
        state: {
          kind: "roster_mapping_required",
          sleeper_roster_ids: ["1"],
          season: historicalSeason,
        },
      }),
    ).toBe(false);
    expect(readinessAllowsGeneration(undefined)).toBe(false);
  });

  it("keys transport arguments by cutoff and preparation mode", () => {
    expect(
      snapshotReadinessPath(COMPETITION_ID, PRIMARY_ID, {
        throughWeek: 12,
        mode: "live",
      }),
    ).toBe(
      `/api/v1/data/competitions/${COMPETITION_ID}/seasons/${PRIMARY_ID}/snapshot-readiness?through_week=12&mode=live`,
    );
  });
});

describe("snapshot readiness rendering", () => {
  it("renders complete ready coverage", () => {
    const html = renderPanel(ready);

    expect(html).toContain("Ready to generate");
    expect(html).toContain("2025, 2026");
    expect(html).toContain("aaaaaaaaaaaa…");
  });

  it("renders refresh preparation without blocking generation", () => {
    const html = renderPanel({
      ...ready,
      state: {
        kind: "refresh_required",
        reason: "stale",
        missing_scopes: [],
        season: primarySeason,
      },
    });

    expect(html).toContain("2026 needs a stale refresh through week 8");
    expect(html).toContain("You may generate now");
    expect(html).toContain("Prepare now");
  });

  it("links mapping blockers to the exact historical season", () => {
    const html = renderPanel({
      ...ready,
      state: {
        kind: "roster_mapping_required",
        sleeper_roster_ids: ["1", "2"],
        season: historicalSeason,
      },
    });

    expect(html).toContain("2025 needs team identity mapping for 2 rosters");
    expect(html).toContain(
      `/competitions/${COMPETITION_ID}?season=${HISTORY_ID}`,
    );
  });

  it("blocks unknown readiness and exposes a bounded retry", () => {
    const html = renderPanel(undefined, {
      readinessError: new Error("timeout"),
    });

    expect(html).toContain("Generation is blocked until the check succeeds");
    expect(html).toContain("Retry readiness");
  });

  it("directs a preparation mapping failure to its exact season", () => {
    const mappingError = normalizeApiError(409, {
      error: {
        code: "roster_identity_mapping_required",
        summary: "mapping required",
        competition_season_id: HISTORY_ID,
        sleeper_roster_ids: ["1", "2"],
      },
    });
    const html = renderPanel(
      {
        ...ready,
        state: {
          kind: "refresh_required",
          reason: "missing",
          missing_scopes: [],
          season: historicalSeason,
        },
      },
      { preparationError: mappingError },
    );

    expect(mappingError.competitionSeasonId).toBe(HISTORY_ID);
    expect(mappingError.sleeperRosterIds).toEqual(["1", "2"]);
    expect(html).toContain(
      "Preparation found a historical team identity blocker",
    );
    expect(html).toContain(
      `/competitions/${COMPETITION_ID}?season=${HISTORY_ID}`,
    );
  });
});

describe("preparation invalidation coverage", () => {
  it("includes receipt seasons and mapping failures", () => {
    const response = {
      refresh_receipts: [
        {
          claim_id: "30000000-0000-0000-0000-000000000001",
          competition_season_id: HISTORY_ID,
          disposition: "claimed",
          refresh_run_id: "40000000-0000-0000-0000-000000000001",
          status: "succeeded",
          through_week: 18,
        },
      ],
    } as SnapshotPreparationResponse;
    expect(preparationAffectedSeasonIds(PRIMARY_ID, response, null)).toEqual([
      PRIMARY_ID,
      HISTORY_ID,
    ]);

    const mappingError = new ApiError({
      status: 409,
      code: "roster_identity_mapping_required",
      summary: "mapping required",
      competitionSeasonId: HISTORY_ID,
      sleeperRosterIds: ["1", "2"],
    });
    expect(
      preparationAffectedSeasonIds(PRIMARY_ID, undefined, mappingError),
    ).toEqual([PRIMARY_ID, HISTORY_ID]);
    expect(
      preparationInvalidationKeys(
        COMPETITION_ID,
        PRIMARY_ID,
        undefined,
        mappingError,
      ),
    ).toEqual([
      [
        "competitions",
        COMPETITION_ID,
        "seasons",
        PRIMARY_ID,
        "snapshot-readiness",
      ],
      ["competitions", COMPETITION_ID, "seasons", PRIMARY_ID, "snapshots"],
      ["competitions", COMPETITION_ID, "seasons", PRIMARY_ID, "refreshes"],
      ["competitions", COMPETITION_ID, "seasons", PRIMARY_ID],
      [
        "competitions",
        COMPETITION_ID,
        "seasons",
        PRIMARY_ID,
        "roster-mappings",
      ],
      ["competitions", COMPETITION_ID, "seasons", HISTORY_ID, "refreshes"],
      ["competitions", COMPETITION_ID, "seasons", HISTORY_ID],
      [
        "competitions",
        COMPETITION_ID,
        "seasons",
        HISTORY_ID,
        "roster-mappings",
      ],
    ]);
  });
});
