import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ApiError } from "@/api/errors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateSeason } from "@/features/seasons/queries";

const formSchema = z.object({
  seasonYear: z
    .number({ error: "Enter a season year." })
    .int("Use a four-digit year.")
    .min(1900, "Season year must be 1900 or later.")
    .max(9999, "Season year must use four digits."),
  sleeperLeagueId: z.string().trim().min(1, "Enter the Sleeper league ID."),
});

type FormValues = z.infer<typeof formSchema>;

interface AddSeasonDialogProps {
  competitionId: string;
  disabled?: boolean;
  prominent?: boolean;
  onCreated: (seasonId: string) => void;
}

export function AddSeasonDialog({
  competitionId,
  disabled = false,
  prominent = false,
  onCreated,
}: AddSeasonDialogProps): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const mutation = useCreateSeason(competitionId);
  const {
    formState: { errors },
    handleSubmit,
    register,
    reset,
    setError,
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      seasonYear: new Date().getFullYear(),
      sleeperLeagueId: "",
    },
  });

  function handleOpenChange(nextOpen: boolean): void {
    setOpen(nextOpen);
    if (nextOpen) mutation.reset();
    if (!nextOpen) reset();
  }

  const submit = handleSubmit(async (values) => {
    try {
      const response = await mutation.mutateAsync(values);
      handleOpenChange(false);
      toast.success("Season attached", {
        description: `${String(response.season.season_year)} is ready for its first refresh.`,
      });
      onCreated(response.season.id);
    } catch (error) {
      if (!(error instanceof ApiError)) return;
      const yearMessage = error.fieldErrors.season_year?.[0];
      const leagueMessage = error.fieldErrors.sleeper_league_id?.[0];
      if (yearMessage) setError("seasonYear", { message: yearMessage });
      if (leagueMessage)
        setError("sleeperLeagueId", { message: leagueMessage });
    }
  });

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant={prominent ? "default" : "outline"} disabled={disabled}>
          <Plus className="size-4" aria-hidden="true" />
          Add season
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a Sleeper season</DialogTitle>
          <DialogDescription>
            Sleeper creates a new league ID each season. Attach only the ID that
            belongs to this competition; linked predecessor IDs are not
            inferred.
          </DialogDescription>
        </DialogHeader>
        <form
          className="mt-6 space-y-5"
          onSubmit={(event) => void submit(event)}
          noValidate
        >
          <div className="space-y-2">
            <Label htmlFor="season-year">Season year</Label>
            <Input
              id="season-year"
              type="number"
              min={1900}
              max={9999}
              step={1}
              aria-invalid={errors.seasonYear ? true : undefined}
              aria-describedby={
                errors.seasonYear ? "season-year-error" : undefined
              }
              {...register("seasonYear", { valueAsNumber: true })}
            />
            {errors.seasonYear ? (
              <p id="season-year-error" className="text-sm text-destructive">
                {errors.seasonYear.message}
              </p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="sleeper-league-id">Sleeper league ID</Label>
            <Input
              id="sleeper-league-id"
              autoComplete="off"
              aria-invalid={errors.sleeperLeagueId ? true : undefined}
              aria-describedby={
                errors.sleeperLeagueId ? "sleeper-league-id-error" : undefined
              }
              {...register("sleeperLeagueId")}
            />
            {errors.sleeperLeagueId ? (
              <p
                id="sleeper-league-id-error"
                className="text-sm text-destructive"
              >
                {errors.sleeperLeagueId.message}
              </p>
            ) : null}
          </div>
          {mutation.error ? (
            <p
              role="alert"
              className="rounded-md bg-destructive/10 p-3 text-sm text-destructive"
            >
              {mutation.error instanceof ApiError
                ? mutation.error.message
                : "The season could not be attached."}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                handleOpenChange(false);
              }}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Adding…" : "Add season"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
