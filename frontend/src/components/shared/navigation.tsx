import { LayoutDashboard, Library, PlusCircle, Trophy } from "lucide-react";
import { NavLink } from "react-router";

import { SheetClose } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

interface NavigationProps {
  competitionId?: string;
  closeOnNavigate?: boolean;
}

function NavigationLink({
  to,
  label,
  icon: Icon,
  end,
  closeOnNavigate,
}: {
  to: string;
  label: string;
  icon: typeof Trophy;
  end?: boolean;
  closeOnNavigate: boolean;
}): React.JSX.Element {
  const link = (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
          isActive && "bg-accent text-foreground",
        )
      }
    >
      <Icon className="size-4" aria-hidden="true" />
      {label}
    </NavLink>
  );

  return closeOnNavigate ? <SheetClose asChild>{link}</SheetClose> : link;
}

export function Navigation({
  competitionId,
  closeOnNavigate = false,
}: NavigationProps): React.JSX.Element {
  return (
    <nav aria-label="Primary navigation" className="space-y-1">
      <NavigationLink
        to="/competitions"
        label="Leagues"
        icon={Trophy}
        end
        closeOnNavigate={closeOnNavigate}
      />
      {competitionId ? (
        <>
          <p className="px-3 pb-1 pt-6 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Active league
          </p>
          <NavigationLink
            to={`/competitions/${competitionId}`}
            label="Overview"
            icon={LayoutDashboard}
            end
            closeOnNavigate={closeOnNavigate}
          />
          <NavigationLink
            to={`/competitions/${competitionId}/articles`}
            label="Articles"
            icon={Library}
            closeOnNavigate={closeOnNavigate}
          />
          <NavigationLink
            to={`/competitions/${competitionId}/generate`}
            label="Generate"
            icon={PlusCircle}
            closeOnNavigate={closeOnNavigate}
          />
        </>
      ) : null}
    </nav>
  );
}
