import { Navigate, createBrowserRouter } from "react-router";

import { RouteErrorBoundary } from "@/app/route-error-boundary";
import { AppShell } from "@/app/shell";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: AppShell,
    ErrorBoundary: RouteErrorBoundary,
    children: [
      { index: true, element: <Navigate to="/competitions" replace /> },
      {
        path: "competitions",
        lazy: () => import("@/routes/competitions"),
      },
      {
        path: "competitions/:competitionId",
        lazy: () => import("@/routes/competition-overview"),
      },
      {
        path: "competitions/:competitionId/articles",
        lazy: () => import("@/routes/articles"),
      },
      {
        path: "competitions/:competitionId/generate",
        lazy: () => import("@/routes/generate"),
      },
      {
        path: "competitions/:competitionId/generations/:generationId",
        lazy: () => import("@/routes/generation-detail"),
      },
      { path: "*", lazy: () => import("@/routes/not-found") },
    ],
  },
]);
