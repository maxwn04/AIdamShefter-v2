import { zodResolver } from "@hookform/resolvers/zod";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ApiError } from "@/api/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import type { ManualRefreshResponse } from "@/features/refreshes/api";
import { useManualRefresh } from "@/features/refreshes/queries";

const formSchema = z.object({
  throughWeek: z
    .string()
    .trim()
    .refine(
      (value) => {
        if (value === "") return true;
        const parsed = Number(value);
        return Number.isInteger(parsed) && parsed >= 1 && parsed <= 18;
      },
      { message: "Use a whole week from 1 through 18, or leave it blank." },
    ),
});

type FormValues = z.infer<typeof formSchema>;

interface RefreshSheetProps {
  competitionId: string;
  seasonId: string;
  seasonYear: number;
  leagueName?: string | null;
  disabled?: boolean;
  onOutcome: (outcome: ManualRefreshResponse) => void;
}

export function RefreshSheet({
  competitionId,
  seasonId,
  seasonYear,
  leagueName,
  disabled = false,
  onOutcome,
}: RefreshSheetProps): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const mutation = useManualRefresh(competitionId, seasonId);
  const {
    formState: { errors },
    handleSubmit,
    register,
    reset,
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { throughWeek: "" },
  });

  function handleOpenChange(nextOpen: boolean): void {
    if (mutation.isPending && !nextOpen) return;
    setOpen(nextOpen);
    if (nextOpen) mutation.reset();
    if (!nextOpen) reset();
  }

  const submit = handleSubmit(async ({ throughWeek }) => {
    const parsedWeek = throughWeek === "" ? undefined : Number(throughWeek);
    try {
      const outcome = await mutation.mutateAsync(parsedWeek);
      onOutcome(outcome);
      if (outcome.refresh.status === "succeeded") {
        toast.success("Sleeper refresh succeeded", {
          description: `${String(outcome.refresh.succeeded_request_count)} requests completed successfully.`,
        });
      } else if (outcome.refresh.status === "partial") {
        toast.warning("Sleeper refresh completed partially", {
          description: `${String(outcome.refresh.failed_request_count)} requests failed. Review the outcome before generating.`,
        });
      } else {
        toast.error("Sleeper refresh failed", {
          description: "The failed refresh was recorded for inspection.",
        });
      }
      handleOpenChange(false);
    } catch {
      // The normalized mutation error remains visible in the sheet.
    }
  });

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetTrigger asChild>
        <Button disabled={disabled}>
          <RefreshCw className="size-4" aria-hidden="true" />
          Refresh Sleeper data
        </Button>
      </SheetTrigger>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Refresh Sleeper data</SheetTitle>
          <SheetDescription>
            Fetch the current Sleeper endpoint set for {leagueName ?? "season"}{" "}
            {seasonYear}. This may take several minutes.
          </SheetDescription>
        </SheetHeader>

        <form
          className="flex flex-1 flex-col"
          onSubmit={(event) => void submit(event)}
          noValidate
        >
          <div className="rounded-md border border-border bg-muted/50 p-4 text-sm">
            <p className="font-medium">Selected season</p>
            <p className="mt-1 text-muted-foreground">
              {seasonYear}
              {leagueName ? ` · ${leagueName}` : ""}
            </p>
          </div>

          <div className="mt-6 space-y-2">
            <Label htmlFor="refresh-through-week">
              Through week (optional)
            </Label>
            <Input
              id="refresh-through-week"
              type="number"
              min={1}
              max={18}
              step={1}
              inputMode="numeric"
              placeholder="Derive from NFL state"
              disabled={mutation.isPending}
              aria-invalid={errors.throughWeek ? true : undefined}
              aria-describedby="refresh-through-week-help"
              {...register("throughWeek")}
            />
            <p
              id="refresh-through-week-help"
              className="text-xs leading-5 text-muted-foreground"
            >
              Leave blank to let the backend derive the effective week from the
              current NFL state.
            </p>
            {errors.throughWeek ? (
              <p className="text-sm text-destructive">
                {errors.throughWeek.message}
              </p>
            ) : null}
          </div>

          {mutation.isPending ? (
            <div
              className="mt-6 rounded-md border border-border bg-accent/50 p-4"
              role="status"
              aria-live="polite"
            >
              <p className="font-medium">Fetching Sleeper endpoints…</p>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                League, roster, player, matchup, transaction, and bracket data
                are processed as one recorded refresh.
              </p>
            </div>
          ) : null}

          {mutation.error ? (
            <p
              role="alert"
              className="mt-6 rounded-md bg-destructive/10 p-4 text-sm text-destructive"
            >
              {mutation.error instanceof ApiError
                ? mutation.error.message
                : mutation.error instanceof DOMException &&
                    mutation.error.name === "TimeoutError"
                  ? "The refresh request exceeded five minutes. Check refresh history before retrying."
                  : "The refresh request could not be completed. Check refresh history before retrying."}
            </p>
          ) : null}

          <div className="mt-auto flex flex-col-reverse gap-2 pt-8 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="ghost"
              disabled={mutation.isPending}
              onClick={() => {
                handleOpenChange(false);
              }}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Refreshing…" : "Start refresh"}
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  );
}
