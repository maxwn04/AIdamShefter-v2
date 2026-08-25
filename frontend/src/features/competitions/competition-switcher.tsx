import { Check, ChevronsUpDown, Trophy } from "lucide-react";
import { useNavigate } from "react-router";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCompetitionList } from "@/features/competitions/queries";
import { cn } from "@/lib/utils";

interface CompetitionSwitcherProps {
  competitionId?: string;
}

const switcherParameters = {
  includeArchived: false,
  limit: 200,
  offset: 0,
} as const;

export function CompetitionSwitcher({
  competitionId,
}: CompetitionSwitcherProps): React.JSX.Element {
  const navigate = useNavigate();
  const query = useCompetitionList(switcherParameters);
  const competitions = query.data?.page.items ?? [];
  const active = competitions.find(
    ({ competition }) => competition.id === competitionId,
  );

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          className="w-full justify-between overflow-hidden bg-background"
          aria-label="Choose active league"
        >
          <span className="flex min-w-0 items-center gap-2">
            <Trophy className="size-4 shrink-0" aria-hidden="true" />
            <span className="truncate">
              {active?.competition.display_name ?? "Choose a league"}
            </span>
          </span>
          <ChevronsUpDown
            className="size-4 shrink-0 text-muted-foreground"
            aria-hidden="true"
          />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60">
        <DropdownMenuLabel>Active leagues</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {query.isPending ? (
          <DropdownMenuItem disabled>Loading leagues…</DropdownMenuItem>
        ) : query.isError ? (
          <DropdownMenuItem disabled>Leagues unavailable</DropdownMenuItem>
        ) : competitions.length === 0 ? (
          <DropdownMenuItem disabled>No leagues yet</DropdownMenuItem>
        ) : (
          competitions.map(({ competition }) => (
            <DropdownMenuItem
              key={competition.id}
              onSelect={() => {
                void navigate(`/competitions/${competition.id}`);
              }}
            >
              <Check
                className={cn(
                  "size-4",
                  competition.id !== competitionId && "invisible",
                )}
                aria-hidden="true"
              />
              <span className="truncate">{competition.display_name}</span>
            </DropdownMenuItem>
          ))
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            void navigate("/competitions");
          }}
        >
          Manage leagues
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
