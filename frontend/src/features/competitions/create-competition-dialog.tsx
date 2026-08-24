import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";
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
import { useCreateCompetition } from "@/features/competitions/queries";

const formSchema = z.object({
  displayName: z.string().trim().min(1, "Enter a league name."),
});

type FormValues = z.infer<typeof formSchema>;

interface CreateCompetitionDialogProps {
  prominent?: boolean;
}

export function CreateCompetitionDialog({
  prominent = false,
}: CreateCompetitionDialogProps): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const mutation = useCreateCompetition();
  const {
    formState: { errors },
    handleSubmit,
    register,
    reset,
    setError,
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { displayName: "" },
  });

  function handleOpenChange(nextOpen: boolean): void {
    setOpen(nextOpen);
    if (nextOpen) mutation.reset();
    if (!nextOpen) reset();
  }

  const submit = handleSubmit(async ({ displayName }) => {
    try {
      const response = await mutation.mutateAsync(displayName);
      handleOpenChange(false);
      toast.success("League created", {
        description: `${response.competition.display_name} is ready for its first season.`,
      });
      await navigate(`/competitions/${response.competition.id}`);
    } catch (error) {
      if (error instanceof ApiError) {
        const message = error.fieldErrors.display_name?.[0];
        if (message) setError("displayName", { message });
      }
    }
  });

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant={prominent ? "default" : "outline"}>
          <Plus className="size-4" aria-hidden="true" />
          Create competition
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create a competition</DialogTitle>
          <DialogDescription>
            A competition is the continuous identity for a fantasy league across
            seasons. You will attach its first Sleeper season next.
          </DialogDescription>
        </DialogHeader>
        <form
          className="mt-6 space-y-5"
          onSubmit={(event) => void submit(event)}
          noValidate
        >
          <div className="space-y-2">
            <Label htmlFor="competition-name">Display name</Label>
            <Input
              id="competition-name"
              autoFocus
              autoComplete="off"
              aria-invalid={errors.displayName ? true : undefined}
              aria-describedby={
                errors.displayName ? "competition-name-error" : undefined
              }
              {...register("displayName")}
            />
            {errors.displayName ? (
              <p
                id="competition-name-error"
                className="text-sm text-destructive"
              >
                {errors.displayName.message}
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
                : "The competition could not be created."}
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
              {mutation.isPending ? "Creating…" : "Create competition"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
