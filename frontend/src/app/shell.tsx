import { Menu, Trophy } from "lucide-react";
import { Link, Outlet, useMatch } from "react-router";

import { ApiStatus } from "@/components/shared/api-status";
import { Breadcrumbs } from "@/components/shared/breadcrumbs";
import { Navigation } from "@/components/shared/navigation";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { CompetitionSwitcher } from "@/features/competitions/competition-switcher";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

export function AppShell(): React.JSX.Element {
  const competitionMatch = useMatch("/competitions/:competitionId/*");
  const competitionId = competitionMatch?.params.competitionId;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#main-content"
        className="sr-only z-[100] rounded-md bg-primary px-4 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        Skip to content
      </a>

      <header className="sticky top-0 z-40 flex h-16 items-center border-b border-border bg-background/95 px-4 backdrop-blur md:hidden">
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Open navigation">
              <Menu className="size-5" aria-hidden="true" />
            </Button>
          </SheetTrigger>
          <SheetContent>
            <SheetHeader>
              <SheetTitle>AIdam Shefter</SheetTitle>
              <SheetDescription>Editorial operations desk</SheetDescription>
            </SheetHeader>
            <div className="mb-5">
              <CompetitionSwitcher competitionId={competitionId} />
            </div>
            <Navigation competitionId={competitionId} closeOnNavigate />
          </SheetContent>
        </Sheet>
        <Link
          to="/competitions"
          className="ml-3 font-editorial text-lg font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          AIdam Shefter
        </Link>
        <div className="ml-auto">
          <ApiStatus />
        </div>
      </header>

      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-border bg-sidebar md:flex md:flex-col">
        <div className="flex h-20 items-center gap-3 px-6">
          <div className="flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Trophy className="size-5" aria-hidden="true" />
          </div>
          <div>
            <Link
              to="/competitions"
              className="font-editorial text-lg font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              AIdam Shefter
            </Link>
            <p className="text-xs text-muted-foreground">
              Editorial operations
            </p>
          </div>
        </div>
        <Separator />
        <div className="px-4 py-4">
          <CompetitionSwitcher competitionId={competitionId} />
        </div>
        <Separator />
        <div className="flex-1 overflow-y-auto px-3 py-5">
          <Navigation competitionId={competitionId} />
        </div>
        <Separator />
        <div className="p-5">
          <ApiStatus />
        </div>
      </aside>

      <main id="main-content" className="md:pl-64">
        <Breadcrumbs competitionId={competitionId} />
        <Outlet />
      </main>
    </div>
  );
}
