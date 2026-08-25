import { MapPinOff } from "lucide-react";
import { Link } from "react-router";

import { buttonVariants } from "@/components/ui/button";

export function Component(): React.JSX.Element {
  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-xl items-center px-6 py-16 text-center md:min-h-screen">
      <div className="w-full">
        <MapPinOff
          className="mx-auto size-9 text-muted-foreground"
          aria-hidden="true"
        />
        <p className="mt-5 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          404
        </p>
        <h1 className="mt-2 font-editorial text-4xl font-semibold">
          This page is off the board.
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          The route does not match an AIdam Shefter workspace.
        </p>
        <Link
          to="/competitions"
          className={buttonVariants({ className: "mt-7" })}
        >
          Return to leagues
        </Link>
      </div>
    </div>
  );
}
