import { ChevronRight } from "lucide-react";
import { Link, useLocation } from "react-router";

import { useCompetitionDetail } from "@/features/competitions/queries";

interface BreadcrumbsProps {
  competitionId?: string;
}

function resourceLabel(pathname: string): string | undefined {
  if (pathname.includes("/articles/")) return "Article";
  if (pathname.endsWith("/articles")) return "Articles";
  if (pathname.endsWith("/generate")) return "Generate";
  if (pathname.includes("/generations/")) return "Generation";
  if (/\/competitions\/[^/]+\/?$/.test(pathname)) return "Overview";
  return undefined;
}

export function Breadcrumbs({
  competitionId,
}: BreadcrumbsProps): React.JSX.Element {
  const { pathname } = useLocation();
  const competitionQuery = useCompetitionDetail(competitionId);
  const label = resourceLabel(pathname);

  return (
    <nav
      aria-label="Breadcrumb"
      className="border-b border-border bg-card/50 px-5 py-3 sm:px-8"
    >
      <ol className="mx-auto flex max-w-6xl items-center gap-2 text-xs text-muted-foreground">
        <li>
          <Link className="hover:text-foreground" to="/competitions">
            Leagues
          </Link>
        </li>
        {competitionId ? (
          <>
            <li aria-hidden="true">
              <ChevronRight className="size-3" />
            </li>
            <li>
              <Link
                className="hover:text-foreground"
                to={`/competitions/${competitionId}`}
              >
                {competitionQuery.data?.competition.display_name ?? "League"}
              </Link>
            </li>
          </>
        ) : null}
        {label ? (
          <>
            <li aria-hidden="true">
              <ChevronRight className="size-3" />
            </li>
            <li className="font-medium text-foreground" aria-current="page">
              {label}
            </li>
          </>
        ) : null}
      </ol>
    </nav>
  );
}
