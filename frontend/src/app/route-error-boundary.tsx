import { CircleAlert } from "lucide-react";
import { isRouteErrorResponse, useRouteError } from "react-router";

import { Button } from "@/components/ui/button";

export function RouteErrorBoundary(): React.JSX.Element {
  const error = useRouteError();
  const summary = isRouteErrorResponse(error)
    ? `${String(error.status)} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "An unexpected page error occurred.";

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
      <section className="w-full max-w-lg rounded-lg border border-border bg-card p-8 shadow-sm">
        <CircleAlert
          className="mb-5 size-8 text-destructive"
          aria-hidden="true"
        />
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Page unavailable
        </p>
        <h1 className="mt-2 font-editorial text-3xl font-semibold">
          The desk hit a snag.
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          {summary}
        </p>
        <Button
          className="mt-6"
          onClick={() => {
            window.location.reload();
          }}
        >
          Reload page
        </Button>
      </section>
    </div>
  );
}
